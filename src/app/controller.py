"""Owns the two native windows and coordinates their lifetime."""
from PyQt6.QtCore import QObject, QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QAction
from .pet_window import PetWindow
from .manager_window import ManagerWindow
from ..utils.sprite import SpriteManager


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


class ApplicationController(QObject):
    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self._browser_workers = set()
        self._shutting_down = False
        self.pet = PetWindow()
        self.pet.command_box.command_submitted.disconnect()
        self.pet.command_box.command_submitted.connect(self.submit)
        self.pet.command_box.voice_command_submitted.disconnect()
        self.pet.command_box.voice_command_submitted.connect(self.submit_voice)
        self.pet.command_box.input_field.setPlaceholderText('Hi!!')
        self.pet.command_box.input_field.setMaxLength(500)
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
        if config['x'] is not None and config['y'] is not None:
            self.pet.move(config['x'], config['y'])
        self.pet._keep_on_screen()
        self.pet._update_pet_anchor()
        self.pet.tray_icon.setVisible(self.core.app_settings()['tray'])

    def save_position(self, _position=None):
        self.pet._keep_on_screen()
        self.core.save_position(self.pet.x(), self.pet.y())

    def execute(self, phrase, parent=None):
        result = self.core.execute(phrase, defer_browser=True)
        if 'browser_action' in result:
            worker = BrowserWorker(self.core.launcher, result['browser_action'], result['browser_target'], self)
            self._browser_workers.add(worker)
            worker.completed.connect(lambda success, message, action=worker.action: self._browser_completed(action, success, message))
            worker.finished.connect(lambda: self._release_browser_worker(worker))
            worker.start()
        if 'confirmation' in result:
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

    def _release_browser_worker(self, worker):
        self._browser_workers.discard(worker)
        worker.deleteLater()

    def _browser_completed(self, action, success, message):
        if self._shutting_down:
            return
        result = self.core.finish_browser_action(action, success, message)
        self.pet.response_bubble.show_message(result['message'])
        self.pet.pet.set_state(result['pet_state'], temporary_ms=3000)
        self.pet._reanchor_pet()

    def submit_voice(self, phrase):
        if self._shutting_down:
            return
        canonical = self.core.resolve_voice_phrase(phrase)
        result = self.execute(canonical)
        self.pet.response_bubble.show_message(result['message'])
        self.pet.pet.set_state(result['pet_state'], temporary_ms=3000)
        self.pet._reanchor_pet()
        # Retain failed transcription for correction instead of silently discarding it.
        self.pet.command_box.input_field.setText('' if result['success'] else phrase)

    def submit(self, phrase):
        if self._shutting_down:
            return
        result = self.execute(phrase)
        self.pet.response_bubble.show_message(result['message'])
        self.pet.pet.set_state(result['pet_state'], temporary_ms=3000)
        self.pet._reanchor_pet()

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
        self.manager.refresh()

    def minimize_pet(self):
        self.save_position()
        self.pet.minimize_pet()
        self.manager.refresh()

    def restore_pet(self):
        self.pet.restore_pet()
        self.save_position()
        self.manager.refresh()

    def hide_pet(self):
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
        self._shutting_down = True
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
