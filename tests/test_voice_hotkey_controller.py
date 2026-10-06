"""Controller integration with deterministic listener and microphone stand-ins."""
from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QPushButton
from src.app.controller import ApplicationController
from src.core.application import ApplicationCore
from src.config.settings import settings


class Listener(QObject):
    activated = pyqtSignal()
    released = pyqtSignal()
    status_changed = pyqtSignal(str)

    def start(self):
        self.status_changed.emit('Test listener ready')

    def stop(self):
        self.stopped = True


class Worker(QObject):
    listening_started = pyqtSignal()
    audio_level_changed = pyqtSignal(float)
    partial_recognized = pyqtSignal(str)
    processing_started = pyqtSignal()
    speech_recognized = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, parent=None, hold_to_talk=False):
        super().__init__(parent)
        self.hold_to_talk = hold_to_talk
        self.running = False
        self.finish_recording = MagicMock()
        self.cancel = MagicMock()

    def start(self):
        self.running = True
        self.listening_started.emit()

    def isRunning(self):
        return self.running

    def wait(self):
        self.running = False

    def complete(self, text=None):
        if text:
            self.speech_recognized.emit(text)
        self.running = False
        self.finished.emit()


@pytest.fixture
def app(tmp_path, qapp, monkeypatch):
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    monkeypatch.setattr('src.services.voice_hotkey.VoiceHotkeyListener', Listener)
    monkeypatch.setattr('src.components.command_box.VoiceInputWorker', Worker)
    monkeypatch.setattr('src.components.command_box.is_speech_available', lambda: True)
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened Notepad')
    core = ApplicationCore(tmp_path, launcher)
    controller = ApplicationController(core)
    yield controller
    core.listeners.clear()
    qapp.aboutToQuit.disconnect(controller.shutdown)
    controller.shutdown()
    controller.pet.hide()
    controller.manager.hide()


def enable(app):
    app.core.save_settings(dict(app.core.app_settings(), voice_hotkey_enabled=True))
    return app._voice_hotkey


def test_settings_checkbox_saves_and_displays_listener_status(app):
    app.show_manager('Settings')
    checkbox = next(box for box in app.manager.findChildren(QCheckBox)
                    if box.text() == 'Enable Ctrl + Windows for voice input')
    assert not checkbox.isChecked()
    checkbox.setChecked(True)
    next(b for b in app.manager.findChildren(QPushButton) if b.text() == 'Save preferences').click()
    assert app.core.app_settings()['voice_hotkey_enabled']
    assert app.voice_hotkey_status == 'Test listener ready'
    app._voice_hotkey.status_changed.emit('Voice shortcut could not start')
    assert app.voice_hotkey_status == 'Voice shortcut could not start'


def test_hotkey_shows_pet_once_and_release_only_finishes_owned_worker(app):
    listener = enable(app)
    app.hide_pet()
    listener.activated.emit()
    box = app.pet.command_box
    worker = box._voice_worker
    assert app.pet.isVisible() and box.isVisible()
    assert worker.hold_to_talk
    listener.activated.emit()
    assert box._voice_worker is worker
    listener.released.emit()
    worker.finish_recording.assert_called_once()
    worker.complete('open notepad')
    app.core.launcher.open_application.assert_called_once_with('notepad')
    assert app._hotkey_voice_worker is None
    assert box._start_voice_input()
    microphone_worker = box._voice_worker
    assert not microphone_worker.hold_to_talk
    listener.activated.emit()
    listener.released.emit()
    microphone_worker.finish_recording.assert_not_called()
    microphone_worker.complete()


@pytest.mark.parametrize('action', ['hide', 'disable', 'direct_hide'])
def test_hiding_or_disabling_cancels_hotkey_recording(app, action):
    listener = enable(app)
    listener.activated.emit()
    worker = app.pet.command_box._voice_worker
    if action == 'hide':
        app.hide_pet()
    elif action == 'direct_hide':
        app.pet.hide()
    else:
        app.core.save_settings(dict(app.core.app_settings(), voice_hotkey_enabled=False))
        assert listener.stopped
    assert app.pet.command_box._voice_cancelled
    worker.cancel.assert_called()
    listener.released.emit()
    worker.finish_recording.assert_not_called()
    worker.complete('open notepad')
    app.core.launcher.open_application.assert_not_called()


def test_shortcut_restores_minimized_pet(app):
    listener = enable(app)
    app.minimize_pet()
    listener.activated.emit()
    assert not app.pet.pet_minimized
    assert app.pet.command_box._voice_worker.hold_to_talk
    app.pet.command_box._voice_worker.complete()


def test_shutdown_cancels_recording_and_stops_listener(app, monkeypatch):
    listener = enable(app)
    listener.activated.emit()
    worker = app.pet.command_box._voice_worker
    close = MagicMock()
    with monkeypatch.context() as patch:
        patch.setattr(app.core, 'close', close)
        app.shutdown()
    assert listener.stopped
    worker.cancel.assert_called()
    close.assert_called_once()
    # The fixture still closes the isolated core after this lifecycle check.
    app._shutting_down = False


@pytest.fixture
def typing_service(app):
    service = MagicMock()
    service.capture_target.return_value = object()
    service.target_is_current.return_value = True
    service.modifiers_released.return_value = True
    service.insert_text.return_value = (True, 'Text inserted.')
    app._typing_service = service
    return service


def test_dictation_capture_before_display_and_no_history(app, typing_service, monkeypatch):
    order = []
    target = typing_service.capture_target.return_value
    typing_service.capture_target.side_effect = lambda: (order.append('capture') or target)
    original = app.show_pet
    def show():
        order.append('show')
        original()
    monkeypatch.setattr(app, 'show_pet', show)
    listener = enable(app)
    listener.activated.emit()
    assert order == ['capture', 'show']
    focus = MagicMock()
    monkeypatch.setattr(app.pet.command_box.input_field, 'setFocus', focus)
    execute = MagicMock()
    monkeypatch.setattr(app, 'execute', execute)
    app.pet.command_box._voice_worker.complete('type how are you question mark')
    typing_service.insert_text.assert_called_once_with(target, 'How are you?')
    execute.assert_not_called()
    focus.assert_not_called()
    assert not app.pet.command_box.input_field.text()
    assert app._typing_target is None and app._pending_dictation is None


def test_dictation_waits_for_modifiers_after_worker_finishes(app, typing_service):
    listener = enable(app)
    listener.activated.emit()
    target = app._typing_target
    typing_service.modifiers_released.return_value = False
    app.pet.command_box._voice_worker.complete('type hello')
    typing_service.insert_text.assert_not_called()
    assert app._pending_dictation is not None
    typing_service.modifiers_released.return_value = True
    app._try_dictation()
    typing_service.insert_text.assert_called_once_with(target, 'Hello')


@pytest.mark.parametrize('reason', ['focus', 'timeout', 'hide', 'disable', 'cancel'])
def test_dictation_cancel_does_not_type(app, typing_service, monkeypatch, reason):
    listener = enable(app)
    listener.activated.emit()
    worker = app.pet.command_box._voice_worker
    typing_service.modifiers_released.return_value = False
    if reason == 'cancel':
        app.pet.command_box._cancel_voice_input()
    worker.complete('type private words')
    if reason == 'focus':
        typing_service.target_is_current.return_value = False
    elif reason == 'timeout':
        monkeypatch.setattr('src.app.controller.time.monotonic', lambda: 10**12)
    elif reason == 'hide':
        app.hide_pet()
    elif reason == 'disable':
        app.core.save_settings(dict(app.core.app_settings(), voice_hotkey_enabled=False))
    app._try_dictation()
    typing_service.insert_text.assert_not_called()
    assert app._pending_dictation is None and app._typing_target is None


def test_empty_dictation_is_not_a_command(app, typing_service, monkeypatch):
    listener = enable(app)
    listener.activated.emit()
    execute = MagicMock()
    monkeypatch.setattr(app, 'execute', execute)
    app.pet.command_box._voice_worker.complete('type,')
    execute.assert_not_called()
    typing_service.insert_text.assert_not_called()
    assert app._typing_target is None


def test_old_recognition_cannot_insert_into_new_session(app, typing_service):
    listener = enable(app)
    listener.activated.emit()
    old = app.pet.command_box._voice_worker
    old.complete()
    listener.activated.emit()
    old.speech_recognized.emit('type wrong session')
    typing_service.insert_text.assert_not_called()
    app.pet.command_box._voice_worker.complete('type right session')
    assert typing_service.insert_text.call_args.args[1] == 'Right session'



def test_hotkey_panel_shows_without_activation(app, typing_service):
    from PyQt6.QtCore import Qt
    listener = enable(app)
    app.pet.hide()
    listener.activated.emit()
    assert app.pet.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert app.pet.command_box._voice_preserve_focus
    app.pet.command_box._voice_worker.complete()
    assert not app.pet.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_recognition_error_clears_target(app, typing_service):
    listener = enable(app)
    listener.activated.emit()
    worker = app.pet.command_box._voice_worker
    worker.error_occurred.emit('No clear speech detected.')
    worker.complete()
    assert app._typing_target is None and app._pending_dictation is None
    typing_service.insert_text.assert_not_called()


def test_microphone_type_still_uses_normal_command_flow(app, typing_service, monkeypatch):
    execute = MagicMock(return_value=dict(success=False, message='Unsupported command.', pet_state='idle'))
    monkeypatch.setattr(app, 'execute', execute)
    assert app.pet.command_box._start_voice_input()
    app.pet.command_box._voice_worker.complete('type hello')
    execute.assert_called_once_with('type hello')
    typing_service.insert_text.assert_not_called()


def test_stale_worker_finish_cannot_clear_new_session(app, typing_service):
    listener = enable(app)
    listener.activated.emit()
    old = app.pet.command_box._voice_worker
    old.complete()
    listener.activated.emit()
    new = app.pet.command_box._voice_worker
    old.finished.emit()
    assert app.pet.command_box._voice_worker is new
    assert app.pet.command_box._voice_active
    new.complete('type hello')
    typing_service.insert_text.assert_called_once()
