"""Speech bar transitions and voice-specific command routing."""
from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from src.components.command_box import CommandBoxWidget
from src.app.controller import ApplicationController
from src.core.application import ApplicationCore


class ControlledWorker(QObject):
    listening_started = pyqtSignal()
    audio_level_changed = pyqtSignal(float)
    partial_recognized = pyqtSignal(str)
    processing_started = pyqtSignal()
    speech_recognized = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.cancelled = False
    def start(self):
        self.running = True
    def isRunning(self):
        return self.running
    def cancel(self):
        self.cancelled = True
    def finish(self):
        self.running = False
        self.finished.emit()


@pytest.fixture
def voice_box(qtbot, monkeypatch):
    monkeypatch.setattr('src.components.command_box.SPEECH_AVAILABLE', True)
    monkeypatch.setattr('src.components.command_box.VoiceInputWorker', ControlledWorker)
    box = CommandBoxWidget()
    qtbot.addWidget(box)
    box.show()
    return box


def test_mic_immediately_converts_input_to_speech_bar(voice_box):
    box = voice_box
    box.input_field.setText('unfinished typed command')
    box.voice_button.click()
    assert box._voice_active and not box.voice_bar.isHidden()
    assert box.input_field.isHidden() and box.send_button.isHidden() and box.voice_button.isHidden()
    assert not box.cancel_voice_button.isHidden()
    assert box.voice_status.text() == 'Starting…'
    worker = box._voice_worker
    worker.listening_started.emit()
    assert box.voice_status.text() == 'Listening…'
    assert box.waveform.timer.isActive()
    worker.audio_level_changed.emit(0.8)
    box.waveform._advance()
    assert box.waveform.levels[-1] > 0
    worker.partial_recognized.emit('play shape of you')
    assert box.voice_status.toolTip() == 'play shape of you'
    box.cancel_voice_button.click()
    assert worker.cancelled
    worker.speech_recognized.emit('wrong command')
    worker.finish()
    assert not box._voice_active and box.voice_bar.isHidden()
    assert not box.input_field.isHidden() and not box.send_button.isHidden()
    assert not box.waveform.timer.isActive()
    assert box.input_field.text() == 'unfinished typed command'


def test_transcription_only_submits_voice_signal_and_restores(voice_box):
    box = voice_box
    typed, spoken = [], []
    box.command_submitted.connect(typed.append)
    box.voice_command_submitted.connect(spoken.append)
    box.voice_button.click()
    worker = box._voice_worker
    worker.listening_started.emit()
    worker.processing_started.emit()
    assert box.voice_status.text() == 'Recognizing…'
    assert not box.waveform.timer.isActive()
    worker.speech_recognized.emit('play shape of you')
    assert spoken == ['play shape of you'] and not typed
    assert box._voice_active  # No retry until the worker has actually finished.
    worker.finish()
    assert not box._voice_active
    assert box.input_field.text() == 'play shape of you'


def test_voice_error_remains_visible_and_allows_retry(voice_box):
    box = voice_box
    box.voice_button.click()
    worker = box._voice_worker
    worker.error_occurred.emit('Check your microphone')
    worker.finish()
    assert box.input_field.placeholderText() == 'Check your microphone'
    box.voice_button.click()
    assert box._voice_active
    box._voice_worker.finish()


@pytest.mark.parametrize('spoken,target', [('open google chrome','chrome'), ('open note pad','notepad'), ('open the calculator','calculator'), ('open visual studio code','vscode')])
def test_voice_aliases_resolve_registered_commands(tmp_path, spoken, target):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened application')
    core = ApplicationCore(tmp_path, launcher)
    try:
        canonical = core.resolve_voice_phrase(spoken)
        assert canonical == 'open ' + target
        assert core.execute(spoken)['success']  # Typed and speech aliases share interpretation.
        launcher.open_application.assert_called_once_with(target)
    finally:
        core.close()


def test_disabled_command_cannot_be_opened_by_voice_alias(tmp_path):
    launcher = MagicMock()
    core = ApplicationCore(tmp_path, launcher)
    try:
        command = next(c for c in core.commands() if c['target'] == 'chrome')
        core.save_command(command['name'], 'application', 'chrome', command['phrases'], False, command['id'])
        assert core.resolve_voice_phrase('open google chrome') == 'open google chrome'
        assert not core.execute(core.resolve_voice_phrase('open google chrome'))['success']
        launcher.open_application.assert_not_called()
    finally:
        core.close()


@pytest.mark.parametrize('spoken', ['play shape of you', 'Shape of You பாட்டு play பண்ணு'])
def test_spoken_play_shape_of_you_uses_same_launcher_as_typed(qtbot, tmp_path, monkeypatch, spoken):
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    launcher = MagicMock()
    launcher.play_youtube.return_value = (True, 'Playing your song')
    core = ApplicationCore(tmp_path, launcher)
    controller = ApplicationController(core)
    try:
        controller.pet.command_box.voice_command_submitted.emit(spoken)
        qtbot.waitUntil(lambda: not controller._browser_workers, timeout=5000)
        launcher.play_youtube.assert_called_once_with('shape of you')
        assert core.history()[0]['execution_status'] == 'success'
    finally:
        controller.shutdown()
        controller.pet.hide()
        controller.manager.hide()
        QApplication.instance().aboutToQuit.disconnect(controller.shutdown)
