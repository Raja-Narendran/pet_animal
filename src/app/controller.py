"""Owns the two native windows and coordinates their lifetime."""
from PyQt6.QtCore import QObject, Qt, QThread, QEvent, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QAction
from .pet_window import PetWindow
from .manager_window import ManagerWindow
from ..utils.sprite import SpriteManager
from ..config.settings import settings
from ..services.voice_input import is_speech_available
from ..services.file_search import FileSearchResponse, FileSearchService
import threading
import time
from ..services.windows_typing import WindowsTypingService, parse_dictation


class BrowserWorker(QThread):
    completed = pyqtSignal(bool, str)

    def __init__(self, launcher, action, target, parent):
        super().__init__(parent)
        self.launcher, self.action, self.target = launcher, action, target

    def run(self):
        try:
            handler = self.launcher.search_web if self.action == 'search' else self.launcher.play_youtube
            success, message = handler(self.target)
        except Exception:
            success, message = False, 'The browser action could not be executed.'
        self.completed.emit(success, message)


class FileSearchWorker(QThread):
    completed = pyqtSignal(object)

    def __init__(self, service, intent, token, parent):
        super().__init__(parent)
        self.service, self.intent, self.token = service, intent, token
        self.cancel_event = threading.Event()
        self.opened_history = parent.core.file_open_records()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            response = self.service.search(self.intent, cancel=self.cancel_event)
            if isinstance(self.service, FileSearchService):
                response = self.service.merge_activity(response, self.intent, self.opened_history, cancel=self.cancel_event)
        except Exception:
            response = FileSearchResponse(partial=True, notice='File search could not finish. Review Settings → Local file search.')
        if not self.cancel_event.is_set():
            self.completed.emit(response)


class WorkflowActionWorker(QThread):
    completed = pyqtSignal(str, bool)

    def __init__(self, run_id, step, launcher, parent):
        super().__init__(parent)
        self.run_id, self.step, self.launcher = run_id, step, launcher

    def run(self):
        try:
            if self.step.type == 'application':
                success, _ = self.launcher.open_application(self.step.value)
            elif self.step.type == 'url':
                success, _ = self.launcher.open_registered_url(self.step.value)
            else:
                success, _ = self.launcher.open_local_result(self.step.value, is_folder=self.step.type == 'folder')
        except Exception:
            success = False
        self.completed.emit(self.run_id, bool(success))


class ApplicationController(QObject):
    workflow_updated = pyqtSignal(object)
    voice_hotkey_status_changed = pyqtSignal(str)

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self._voice_hotkey = None
        self._voice_hotkey_enabled = False
        self._hotkey_voice_worker = None
        self._typing_service = WindowsTypingService()
        self._typing_target = None
        self._pending_dictation = None
        self._dictation_timer = QTimer(self)
        self._dictation_timer.setInterval(20)
        self._dictation_timer.timeout.connect(self._try_dictation)
        self.voice_hotkey_status = 'Voice shortcut is disabled.'
        self._workflow_worker = None
        self._workflow_timer = QTimer(self)
        self._workflow_timer.setSingleShot(True)
        self._workflow_timer.timeout.connect(self._workflow_wait_finished)
        self.last_workflow_result = None
        self._browser_workers = set()
        self._file_workers = set()
        self._shutting_down = False
        self._shortcut_dismissed = False
        self._shortcut_submitting = False
        self.pet = PetWindow()
        self.pet.installEventFilter(self)
        self.pet.command_box.command_submitted.disconnect()
        self.pet.command_box.command_submitted.connect(self.submit)
        self.pet.command_box.voice_command_submitted.disconnect()
        self.pet.command_box.voice_command_submitted.connect(self.submit_voice)
        self.pet.command_box.input_field.setPlaceholderText('Hi!!')
        self.pet.command_box.input_field.setToolTip('Use @ to open an app, /name to find a file, or /name folder to find a folder.')
        self.pet.command_box.input_field.setMaxLength(500)
        self.pet.command_box.input_field.textChanged.connect(self._shortcut_text_changed)
        self.pet.command_box.input_field.installEventFilter(self)
        self.pet.response_bubble.application_selected.connect(self._application_selected)
        self.pet.response_bubble.file_selected.connect(self._file_selected)
        self.pet.response_bubble.file_sort_selected.connect(self._file_sort_selected)
        self.pet.response_bubble.file_dismissed.connect(self._dismiss_file_results)
        self.pet.close_btn.clicked.disconnect()
        self.pet.close_btn.clicked.connect(self.hide_pet)
        self.pet.close_btn.setToolTip('Hide floating pet')
        self.pet.min_btn.clicked.disconnect()
        self.pet.min_btn.clicked.connect(self.minimize_pet)
        self.pet.min_btn.setToolTip('Minimize pet (keep chat box)')
        self.pet.command_box.expand_clicked.connect(self.restore_pet)
        self.pet.command_box.drag_finished.connect(self.save_position)
        self.pet.close_application = self.quit
        self.pet.show_help = lambda: self.submit('help')
        self.pet.pet.drag_finished.connect(self.save_position)
        self.pet.pet.pet_clicked.disconnect()
        self.pet.pet.pet_clicked.connect(self.on_pet_clicked)
        self._appearance = None
        self.core.listeners.append(self.apply)
        self.manager = ManagerWindow(core, self)
        self._configure_tray()
        self.apply()
        if core.app_settings()['launch_pet']:
            self.pet.show()
        if not core.app_settings()['start_minimized'] or not self.pet.tray_icon.isVisible():
            self.manager.show()
        self.manager.refresh()
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def _configure_tray(self):
        self.pet.tray_menu.clear()
        for title, callback in [('Show Floating Pet', self.show_pet), ('Open Manager', self.show_manager), ('Hide Floating Pet', self.hide_pet), ('Settings', lambda: self.show_manager('Settings')), ('Quit', self.quit)]:
            action = QAction(title, self.pet)
            action.triggered.connect(callback)
            self.pet.tray_menu.addAction(action)
        self.pet.tray_icon.activated.disconnect()
        self.pet.tray_icon.activated.connect(lambda reason: self.show_manager() if reason == self.pet.tray_icon.ActivationReason.DoubleClick else None)
        self.pet.tray_icon.setToolTip('Pet Animal')

    def apply(self):
        profile = self.core.active_profile()
        config = profile['config']
        visible = self.pet.isVisible()
        self.pet.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, config['always_on_top'])
        if visible:
            self.pet.show()
        appearance = (profile['selected_asset_id'], config['size'])
        if appearance != self._appearance:
            manager = SpriteManager(config['size'], config['size'])
            frames = manager._slice_sprite_sheet(str(self.core.asset_path(profile['selected_asset_id'])))
            if not frames:
                raise ValueError('Unable to render selected pet asset.')
            # Builtin idle uses the complete existing animation set; other sheets are standalone pets.
            if profile['selected_asset_id'] != 'builtin-idle':
                manager._cache = {state: frames for state in manager._cache}
            self.pet.pet.sprite_manager = manager
            self.pet.pet.setFixedSize(config['size'], config['size'])
            self.pet.pet.set_state('idle')
            self._appearance = appearance
        if config['animations']:
            self.pet.pet.anim_timer.start()
        else:
            self.pet.pet.anim_timer.stop()
        self.pet.setWindowTitle(profile['name'])
        self.pet.command_box.setFixedWidth(config['chat_width'])
        self.pet.command_box.BORDER_RADIUS = config['radius']
        self.pet.command_box.background_color = config['background']
        self.pet.command_box.background_opacity = config['opacity']
        font = self.pet.command_box.input_field.font()
        font.setPixelSize(config['text_size'])
        self.pet.command_box.input_field.setFont(font)
        self.pet.command_box.update()
        self.pet.adjustSize()
        self.pet._ensure_layout_width()
        if config['x'] is not None and config['y'] is not None:
            self.pet.move(config['x'], config['y'])
        self.pet._keep_on_screen()
        self.pet._update_pet_anchor()
        app_settings = self.core.app_settings()
        self.pet.tray_icon.setVisible(app_settings['tray'])
        settings.VOICE_MODE = app_settings.get('voice_mode', 'google')
        settings.GOOGLE_VOICE_LANGUAGE = app_settings.get('google_voice_language', 'en-IN')
        settings.VOICE_MULTILINGUAL = settings.VOICE_MODE == 'multilingual'
        voice_button = self.pet.command_box.voice_button
        if is_speech_available():
            voice_button.setEnabled(True)
            voice_button.setCursor(Qt.CursorShape.PointingHandCursor)
            if not self.pet.command_box._voice_active:
                voice_button.set_idle()
        else:
            voice_button.set_unavailable()
        self._configure_voice_hotkey(app_settings.get('voice_hotkey_enabled', False))
        self._refresh_application_suggestions()

    def _set_voice_hotkey_status(self, message):
        if not self._shutting_down:
            self.voice_hotkey_status = message
            self.voice_hotkey_status_changed.emit(message)

    def _configure_voice_hotkey(self, enabled):
        if self._shutting_down or enabled == self._voice_hotkey_enabled:
            return
        self._voice_hotkey_enabled = enabled
        if self._voice_hotkey is not None:
            self._cancel_hotkey_voice()
            self._voice_hotkey.stop()
            self._voice_hotkey.deleteLater()
            self._voice_hotkey = None
        if enabled:
            from ..services.voice_hotkey import VoiceHotkeyListener
            listener = VoiceHotkeyListener(self)
            self._voice_hotkey = listener
            listener.activated.connect(self._start_hotkey_voice)
            listener.released.connect(self._finish_hotkey_voice)
            listener.status_changed.connect(lambda message: self._set_voice_hotkey_status(message)
                if self._voice_hotkey is listener else None)
            self._set_voice_hotkey_status('Starting voice shortcut...')
            listener.start()
        else:
            self._set_voice_hotkey_status('Voice shortcut is disabled.')

    def _start_hotkey_voice(self):
        if self.sender() is not None and self.sender() is not self._voice_hotkey:
            return
        if self._shutting_down or not self._voice_hotkey_enabled:
            return
        box = self.pet.command_box
        if self._pending_dictation or box._voice_active or (box._voice_worker and box._voice_worker.isRunning()):
            return
        self._typing_target = self._typing_service.capture_target()
        self.pet.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.show_pet()
        self.pet.command_box.show()
        self.pet._reanchor_pet()
        self.pet.response_bubble.dismiss_suggestions()
        self.pet.response_bubble.dismiss_files()
        if box._start_voice_input(hold_to_talk=True):
            worker = box._voice_worker
            self._hotkey_voice_worker = worker
            worker.finished.connect(lambda: self._clear_hotkey_voice(worker))
        else:
            self._clear_dictation()
            self.pet._on_voice_error('Voice input is unavailable. Check microphone and selected engine dependencies.')

    def _clear_hotkey_voice(self, worker):
        if self._hotkey_voice_worker is worker:
            self._hotkey_voice_worker = None
            if self._pending_dictation is None:
                self._clear_dictation()

    def _finish_hotkey_voice(self):
        if self.sender() is not None and self.sender() is not self._voice_hotkey:
            return
        if self._shutting_down or not self._voice_hotkey_enabled:
            return
        worker = self._hotkey_voice_worker
        if worker is not None and worker is self.pet.command_box._voice_worker:
            worker.finish_recording()

    def _cancel_hotkey_voice(self):
        self._clear_dictation()
        worker = self._hotkey_voice_worker
        if worker is not None and worker is self.pet.command_box._voice_worker:
            self.pet.command_box._cancel_voice_input()
        self._hotkey_voice_worker = None

    def _shortcut_text_changed(self, _text):
        self._shortcut_dismissed = False
        self._refresh_application_suggestions(preserve_selection=False)

    def _refresh_application_suggestions(self, preserve_selection=True):
        if self._shutting_down or self._shortcut_submitting:
            return
        box, bubble = self.pet.command_box, self.pet.response_bubble
        phrase = box.input_field.text().strip()
        if (not phrase.startswith('@') or self._shortcut_dismissed or box._voice_active
                or not self.pet.isVisible() or not box.input_field.isVisible()):
            bubble.dismiss_suggestions()
            return
        selected = bubble.selected_application if preserve_selection and bubble.suggestion_mode else None
        bubble.show_suggestions(self.core.application_shortcuts(phrase[1:]), selected)

    def eventFilter(self, watched, event):
        # Qt can dispatch events during QObject construction and after shutdown.
        pet = getattr(self, 'pet', None)
        if pet is not None and not self._shutting_down and watched is pet and event.type() == QEvent.Type.Hide:
            self._cancel_hotkey_voice()
        if pet is not None and not self._shutting_down and watched is pet.command_box.input_field:
            bubble = pet.response_bubble
            if event.type() == QEvent.Type.Hide:
                bubble.dismiss_suggestions()
            elif event.type() == QEvent.Type.KeyPress and (bubble.suggestion_mode or bubble.file_mode) and bubble.isVisible():
                if bubble.file_mode and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not watched.text().strip():
                    if bubble.selected_file:
                        self._file_selected(bubble.file_token, bubble.selected_file)
                    return True
                if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                    bubble.move_selection(-1 if event.key() == Qt.Key.Key_Up else 1)
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    if bubble.file_mode:
                        bubble.dismiss_files()
                        return True
                    self._shortcut_dismissed = True
                    bubble.dismiss_suggestions()
                    return True
        return super().eventFilter(watched, event)

    def _dismiss_file_results(self):
        self.core.file_session.clear()
        self._cancel_superseded_file_workers()

    def _file_selected(self, token, result_id):
        if not self._shutting_down:
            self._show_result(self.core.open_file_result(token, result_id))

    def _file_sort_selected(self, token, order):
        if not self._shutting_down:
            self._show_result(self.core.sort_file_results(token, order))

    def _application_selected(self, target):
        if self._shutting_down or self._shortcut_submitting or not self.pet.response_bubble.suggestion_mode:
            return
        self._launch_application_shortcut(target)

    def _launch_application_shortcut(self, target):
        self._shortcut_submitting = True
        try:
            self.pet.command_box.input_field.clear()
            self.pet.response_bubble.dismiss_suggestions()
            self._show_result(self.core.execute_application_shortcut(target))
            self._cancel_superseded_file_workers()
        finally:
            self._shortcut_submitting = False

    def on_pet_clicked(self):
        """User clicked the floating companion: greet and focus input without moving."""
        self.pet.pet.set_state('greeting', temporary_ms=2500)
        self.pet.command_box.focus_input()

    def save_position(self, _position=None):
        self.pet._keep_on_screen()
        self.pet._update_pet_anchor()
        self.core.save_position(self.pet.x(), self.pet.y())

    def execute(self, phrase, parent=None):
        result = self.core.execute(phrase, defer_browser=True, defer_file_search=True)
        self._cancel_superseded_file_workers()
        if 'routine_id' in result:
            return self.start_routine(result['routine_id'], result.get('routine_phrase'))
        if 'file_search_intent' in result:
            worker = FileSearchWorker(self.core.file_search, result['file_search_intent'], result['file_search_token'], self)
            self._file_workers.add(worker)
            worker.completed.connect(lambda response, w=worker: self._file_search_completed(w, response))
            worker.finished.connect(lambda w=worker: self._release_file_worker(w))
            worker.start()
        if 'browser_action' in result:
            worker = BrowserWorker(self.core.launcher, result['browser_action'], result['browser_target'], self)
            self._browser_workers.add(worker)
            worker.completed.connect(lambda success, message, action=worker.action: self._browser_completed(action, success, message))
            worker.finished.connect(lambda: self._release_browser_worker(worker))
            worker.start()
        if 'memory_confirmation' in result:
            token = result['memory_confirmation']
            if QMessageBox.question(parent or self.pet, 'Confirm memory', result['message'], QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                try:
                    result = self.core.confirm_memory(token)
                except ValueError as error:
                    result = dict(success=False, message=str(error), pet_state='error')
            else:
                self.core.cancel_memory_confirmation(token)
                result = dict(success=False, message='Memory was not changed.', pet_state='idle')
        elif 'confirmation' in result:
            value = result['confirmation']
            if QMessageBox.question(parent or self.pet, 'Confirm memory', result['message'], QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                try:
                    self.core.confirm_name(value)
                    result = dict(success=True, message='Your name is saved.', pet_state='success')
                except Exception as error:
                    result = dict(success=False, message=str(error), pet_state='error')
            else:
                result = dict(success=False, message='Memory was not changed.', pet_state='idle')
        return result

    def start_routine(self, routine_id, phrase=None):
        if self._shutting_down:
            return dict(success=False, message='The application is closing.', pet_state='idle')
        if self._workflow_worker is not None:
            return dict(success=False, message='A routine is already running. Wait for the current action to finish.', pet_state='working')
        try:
            engine = self.core.workflows.start(routine_id, phrase)
        except ValueError as error:
            return dict(success=False, message=str(error), pet_state='error')
        self.last_workflow_result = engine.result
        self.workflow_updated.emit(engine.result)
        if engine.result.status != 'running':
            return dict(success=False, message=engine.result.message, pet_state='error')
        QTimer.singleShot(0, lambda token=engine.result.id: self._workflow_next(token))
        return dict(success=True, message='Starting ' + engine.result.name + '…', pet_state='working')

    def _workflow_progress(self):
        engine = self.core.workflows.active
        if engine:
            self.core.workflows.persist_progress()
            self.last_workflow_result = engine.result
            self.workflow_updated.emit(engine.result)

    def _workflow_next(self, token):
        engine = self.core.workflows.active
        if self._shutting_down or not engine or engine.result.id != token:
            return
        step = engine.begin_step()
        self._workflow_progress()
        if step is None:
            self._workflow_finish()
            return
        try:
            # Main-thread live validation; no database object crosses the boundary.
            self.core.workflows.validate_steps([step.to_dict()], live=True)
        except ValueError:
            engine.complete_step(False, 'target_unavailable')
            self._workflow_progress()
            self._workflow_finish()
            return
        if step.type == 'wait':
            self._workflow_wait_token = token
            self._workflow_timer.start(round(float(step.value) * 1000))
        elif step.type == 'message':
            self._show_result(dict(success=True, message=str(step.value), pet_state='working'))
            self._workflow_action_completed(token, True)
        else:
            from ..services.windows_launcher import WindowsLauncher
            launcher = self.core.launcher
            if isinstance(launcher, WindowsLauncher):
                approved = self.core.get_registered_application(step.value) if step.type == 'application' else None
                launcher = WindowsLauncher(registered_application_lookup=lambda key, app=approved: app if app and app.id == key else None)
                launcher._vscode_path = self.core.launcher._vscode_path
                launcher._chrome_path = self.core.launcher._chrome_path
            worker = WorkflowActionWorker(token, step, launcher, self)
            self._workflow_worker = worker
            worker.completed.connect(self._workflow_action_completed)
            worker.finished.connect(lambda w=worker: self._release_workflow_worker(w))
            worker.start()

    def _release_workflow_worker(self, worker):
        if self._workflow_worker is worker:
            self._workflow_worker = None
        worker.deleteLater()

    def _workflow_wait_finished(self):
        self._workflow_action_completed(self._workflow_wait_token, True)

    def _workflow_action_completed(self, token, success):
        engine = self.core.workflows.active
        if self._shutting_down or not engine or engine.result.id != token:
            return
        engine.complete_step(success)
        self._workflow_progress()
        if engine.result.status == 'running':
            QTimer.singleShot(0, lambda: self._workflow_next(token))
        else:
            self._workflow_finish()

    def _workflow_finish(self):
        engine = self.core.workflows.active
        if not engine:
            return
        self.last_workflow_result = engine.result
        self.core.workflows.finish()
        self.workflow_updated.emit(self.last_workflow_result)
        self._show_result(dict(success=engine.result.status == 'success', message=engine.result.message,
                               pet_state='success' if engine.result.status == 'success' else ('idle' if engine.result.status == 'cancelled' else 'error')))

    def stop_routine(self):
        self._workflow_timer.stop()
        engine = self.core.workflows.active
        if engine:
            engine.cancel()
            self._workflow_finish()

    def _cancel_superseded_file_workers(self):
        for worker in self._file_workers:
            if worker.token != self.core.file_session.token:
                worker.cancel()

    def _file_search_completed(self, worker, response):
        if self._shutting_down or worker.cancel_event.is_set():
            return
        result = self.core.finish_file_search(worker.token, worker.intent, response)
        if result is not None:
            self._show_result(result)

    def _release_file_worker(self, worker):
        self._file_workers.discard(worker)
        worker.deleteLater()

    def _release_browser_worker(self, worker):
        self._browser_workers.discard(worker)
        worker.deleteLater()

    def _browser_completed(self, action, success, message):
        if self._shutting_down:
            return
        result = self.core.finish_browser_action(action, success, message)
        self._show_result(result)

    def _show_result(self, result):
        """Display results from typed, voice, and asynchronous browser commands."""
        if 'file_results' in result:
            self.pet.response_bubble.show_file_results(result)
        elif result.get('file_search'):
            self.pet.response_bubble.show_message(result['message'], timeout_ms=30000, wrap_paths=True)
        else:
            self.pet.response_bubble.show_message(result['message'])
        self.pet.pet.set_state(result['pet_state'], temporary_ms=3000)

    def _clear_dictation(self):
        self._dictation_timer.stop()
        self._pending_dictation = None
        self._typing_target = None
        self.pet.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)

    def _try_dictation(self):
        pending = self._pending_dictation
        if pending is None:
            return
        target, text, deadline = pending
        if self._shutting_down or not self._voice_hotkey_enabled:
            self._clear_dictation()
            return
        if not self._typing_service.target_is_current(target):
            success, message = False, 'Voice typing cancelled: the selected field changed.'
        elif self._typing_service.modifiers_released():
            success, message = self._typing_service.insert_text(target, text)
        elif time.monotonic() < deadline:
            return
        else:
            success, message = False, 'Voice typing cancelled: release all modifier keys.'
        self._clear_dictation()
        self._show_result(dict(success=success, message=message, pet_state='success' if success else 'error'))

    def submit_voice(self, phrase):
        if self._shutting_down:
            return
        worker = self.pet.command_box._voice_worker
        if worker is not None and worker is self._hotkey_voice_worker:
            if self.pet.command_box._voice_cancelled or not self._voice_hotkey_enabled:
                self._clear_dictation()
                return
            text = parse_dictation(phrase)
            if text is not None:
                self.pet.command_box.input_field.clear()
                if self._pending_dictation is not None:
                    return
                if not text:
                    self._clear_dictation()
                    self._show_result(dict(success=False, message='Say type followed by the text to insert.', pet_state='idle'))
                    return
                self._pending_dictation = (self._typing_target, text, time.monotonic() + 2)
                self._dictation_timer.start()
                self._try_dictation()
                return
        result = self.execute(phrase)
        self._show_result(result)
        # Retain failed transcription for correction instead of silently discarding it.
        self.pet.command_box.input_field.setText('' if result['success'] else phrase)

    def submit(self, phrase):
        if self._shutting_down:
            return
        if phrase.strip().startswith('@') and len(phrase) <= 500 and not any(ord(c) < 32 for c in phrase):
            entries = self.core.application_shortcuts(phrase.strip()[1:])
            bubble = self.pet.response_bubble
            target = bubble.selected_application if (bubble.suggestion_mode and
                phrase.strip() == self.pet.command_box.input_field.text().strip()) else None
            if target is not None or entries:
                self._launch_application_shortcut(target if target is not None else entries[0].target)
                return
        result = self.execute(phrase)
        self._show_result(result)

    def show_manager(self, page=None):
        self.manager.show()
        self.manager.raise_()
        self.manager.activateWindow()
        if isinstance(page, str):
            from .manager_window import PAGES
            self.manager.navigation.setCurrentRow(PAGES.index(page))

    def show_pet(self):
        if getattr(self.pet, 'pet_minimized', False):
            self.pet.restore_pet()
        self.pet.show()
        self.pet.raise_()
        self._refresh_application_suggestions()
        self.manager.refresh()

    def minimize_pet(self):
        self.save_position()
        self.pet.minimize_pet()
        self._refresh_application_suggestions()
        self.manager.refresh()

    def restore_pet(self):
        self.pet.restore_pet()
        self.save_position()
        self._refresh_application_suggestions()
        self.manager.refresh()

    def hide_pet(self):
        self._cancel_hotkey_voice()
        self.save_position()
        self.pet.hide()
        # Always leave a path to reopen the companion.
        if not self.pet.tray_icon.isVisible():
            self.show_manager()
        self.manager.refresh()
        if self.core.app_settings()['notifications'] and self.pet.tray_icon.isVisible():
            self.pet.tray_icon.showMessage('Pet Animal', 'Your companion is resting. Use the tray to bring it back.', self.pet.tray_icon.MessageIcon.Information, 1500)

    def quit(self):
        self.save_position()
        self.pet.tray_icon.hide()
        QApplication.instance().quit()

    def shutdown(self):
        if self._shutting_down:
            return
        self.stop_routine()
        self._cancel_hotkey_voice()
        self._shutting_down = True
        if self._voice_hotkey is not None:
            self._voice_hotkey.stop()
        if self._workflow_worker is not None:
            self._workflow_worker.wait()
        for worker in list(self._file_workers):
            worker.cancel()
            worker.wait()
        self.manager.software_state.shutdown()
        self.pet.pet.anim_timer.stop()
        self.pet.tray_icon.hide()
        voice_worker = self.pet.command_box._voice_worker
        if voice_worker and voice_worker.isRunning():
            voice_worker.cancel()
            voice_worker.wait()
        for worker in list(self._browser_workers):
            worker.completed.disconnect()
            worker.wait()
        self.core.close()
