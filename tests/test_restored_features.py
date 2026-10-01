"""Regressions for offline voice and controller browser command dispatch."""
import threading
from unittest.mock import MagicMock
import pytest
from src.core.application import ApplicationCore
from src.app.controller import ApplicationController
from src.services.voice_input import VoiceInputWorker, SoundDeviceMicrophone
from src.services.youtube_automation import YouTubeAutomationService


@pytest.mark.parametrize('phrase,handler,target', [
    ('search for husky pictures', 'search_web', 'husky pictures'),
    ('play shape of you on youtube', 'play_youtube', 'shape of you'),
    ('youtube play faded', 'play_youtube', 'faded'),
])
def test_browser_commands_reach_launcher_without_storing_queries(tmp_path, phrase, handler, target):
    launcher = MagicMock()
    getattr(launcher, handler).return_value = (True, 'Opened')
    core = ApplicationCore(tmp_path, launcher)
    try:
        assert core.execute(phrase)['success']
        getattr(launcher, handler).assert_called_once_with(target)
        assert target not in str(core.history())
    finally:
        core.close()


def test_disabled_registered_phrase_prevents_browser_fallback(tmp_path):
    launcher = MagicMock()
    core = ApplicationCore(tmp_path, launcher)
    try:
        core.save_command('Custom search', 'application', 'notepad', ['search private query'], enabled=False)
        assert not core.execute('search private query')['success']
        launcher.search_web.assert_not_called()
        assert core.history()[0]['trigger_phrase'] == '[unsupported command]'
    finally:
        core.close()


def test_controller_browser_runs_off_main_thread_and_updates_history(qtbot, tmp_path, monkeypatch):
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    release = threading.Event()
    started = threading.Event()
    launcher = MagicMock()
    def play(target):
        started.set()
        assert release.wait(5)
        return True, 'Playback opened'
    launcher.play_youtube.side_effect = play
    core = ApplicationCore(tmp_path, launcher)
    controller = ApplicationController(core)
    try:
        assert not controller.pet.command_box.voice_button.isHidden()
        result = controller.execute('play song example')
        assert result['pet_state'] == 'working'
        assert started.wait(1)
        assert not core.history()
        release.set()
        qtbot.waitUntil(lambda: bool(core.history()), timeout=5000)
        assert core.history()[0]['execution_status'] == 'success'
        launcher.play_youtube.assert_called_once_with('example')
        qtbot.waitUntil(lambda: not controller._browser_workers, timeout=5000)
    finally:
        release.set()
        controller.shutdown()
        controller.pet.hide()
        controller.manager.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.disconnect(controller.shutdown)


def test_microphone_silent_stream_fails_instead_of_hanging():
    import queue
    mic = SoundDeviceMicrophone()
    mic._queue = MagicMock()
    mic._queue.get.side_effect = queue.Empty
    with pytest.raises(OSError, match='stopped delivering audio'):
        mic.read(1024)
    mic._queue.get.assert_called_once_with(timeout=2)


def test_youtube_search_fallback_reports_browser_failure(monkeypatch):
    monkeypatch.setattr(YouTubeAutomationService, 'resolve_original_video_id', lambda song: None)
    monkeypatch.setattr('webbrowser.open', lambda url: False)
    success, message = YouTubeAutomationService.play_song('example')
    assert not success
    assert 'Could not open browser' in message
