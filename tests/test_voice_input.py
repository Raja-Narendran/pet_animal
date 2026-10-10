"""Unit tests for VoiceInputWorker, SoundDeviceMicrophone, and VoiceButton.

All tests are fully offline — no microphone or audio hardware needed.
VoiceInputWorker tests mock the SpeechRecognition recognizer and audio sources.
"""
import pytest
from unittest.mock import patch, MagicMock
from src.components.voice_button import VoiceButton


# ---------------------------------------------------------------------------
# VoiceButton widget tests
# ---------------------------------------------------------------------------

class TestVoiceButtonInitialState:
    """Test VoiceButton starts in the correct idle state."""

    def test_initial_state_is_idle(self, qtbot):
        button = VoiceButton()
        qtbot.addWidget(button)
        assert button._is_listening is False
        assert button.isEnabled() is True
        assert button.text() == "🎤"

    def test_tooltip_idle(self, qtbot):
        button = VoiceButton()
        qtbot.addWidget(button)
        assert "click to speak" in button.toolTip().lower()


class TestVoiceButtonStateTransitions:
    """Test visual state transitions of VoiceButton."""

    def test_set_listening(self, qtbot):
        button = VoiceButton()
        qtbot.addWidget(button)
        button.set_listening()
        assert button._is_listening is True
        assert button.text() == "⏺"
        assert "listening" in button.toolTip().lower()

    def test_set_idle_after_listening(self, qtbot):
        button = VoiceButton()
        qtbot.addWidget(button)
        button.set_listening()
        button.set_idle()
        assert button._is_listening is False
        assert button.text() == "🎤"

    def test_set_unavailable_disables_button(self, qtbot):
        button = VoiceButton()
        qtbot.addWidget(button)
        button.set_unavailable()
        assert button.isEnabled() is False
        assert button._is_listening is False
        assert "unavailable" in button.toolTip().lower()


class TestVoiceButtonSignals:
    """Test signal emission behavior."""

    def test_click_emits_voice_toggled_when_idle(self, qtbot):
        button = VoiceButton()
        qtbot.addWidget(button)
        with qtbot.waitSignal(button.voice_toggled, timeout=1000):
            button.click()

    def test_click_while_listening_does_not_emit(self, qtbot):
        button = VoiceButton()
        qtbot.addWidget(button)
        button.set_listening()
        # Should not emit when already listening
        signals = []
        button.voice_toggled.connect(lambda: signals.append(True))
        button.click()
        assert len(signals) == 0


# ---------------------------------------------------------------------------
# SoundDeviceMicrophone tests
# ---------------------------------------------------------------------------

class TestSoundDeviceMicrophone:
    """Test SoundDeviceMicrophone context manager and stream protocol."""

    @patch("src.services.voice_input.sd")
    def test_mic_context_manager_and_read(self, mock_sd):
        from src.services.voice_input import SoundDeviceMicrophone

        mock_stream = MagicMock()
        mock_sd.RawInputStream.return_value = mock_stream

        mic = SoundDeviceMicrophone()
        with mic as source:
            assert source.stream is not None
            # Simulate audio callback putting data
            source._queue.put(b"audio-chunk-data")
            chunk = source.stream.read(1024)
            assert chunk == b"audio-chunk-data"

        mock_stream.start.assert_called_once()
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert mic.stream is None
        assert mic._queue is None


# ---------------------------------------------------------------------------
# VoiceInputWorker tests use deterministic streaming PCM and recognizer results.
# ---------------------------------------------------------------------------

@pytest.fixture
def streaming_worker(monkeypatch):
    from src.services.voice_input import VoiceInputWorker
    monkeypatch.setattr('src.services.voice_input.settings.VOICE_MODE', 'multilingual')
    monkeypatch.setattr('src.services.voice_input.is_speech_available', lambda mode=None: True)
    monkeypatch.setattr('src.services.voice_input.get_multilingual_model', lambda: object())
    endpoint = MagicMock(started=True)
    endpoint.feed.return_value = True
    monkeypatch.setattr('src.services.voice_input.SpeechEndpoint', lambda silence: endpoint)
    transcribe = MagicMock(return_value='play shape of you')
    monkeypatch.setattr('src.services.voice_input.transcribe_multilingual', transcribe)
    worker = VoiceInputWorker()
    source = MagicMock()
    source.SAMPLE_RATE = 16000
    source.SAMPLE_WIDTH = 2
    source.CHUNK = 1024
    source.stream.read.return_value = bytes(2048)
    source.__enter__.return_value = source
    source.__exit__.return_value = False
    worker._get_microphone = MagicMock(return_value=source)
    return worker, transcribe, source, endpoint


def test_voice_stream_result_and_signal_order(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    events = []
    worker.listening_started.connect(lambda: events.append('listening'))
    worker.processing_started.connect(lambda: events.append('processing'))
    worker.speech_recognized.connect(lambda text: events.append(text))
    worker.listening_stopped.connect(lambda: events.append('stopped'))
    worker.run()
    assert events == ['listening', 'processing', 'play shape of you', 'stopped']
    source.stream.read.assert_called_once_with(1024)


def test_voice_unavailable_still_stops(qtbot, monkeypatch):
    from src.services.voice_input import VoiceInputWorker
    monkeypatch.setattr('src.services.voice_input.is_speech_available', lambda mode=None: False)
    worker = VoiceInputWorker()
    with qtbot.waitSignal(worker.listening_stopped):
        with qtbot.waitSignal(worker.error_occurred) as error:
            worker.run()
    assert 'not available' in error.args[0]


def test_voice_silence_times_out(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    worker.timeout = 0.05
    endpoint.started = False
    endpoint.feed.return_value = False
    source.stream.read.side_effect = lambda size: bytes(2048)
    errors, results = [], []
    worker.error_occurred.connect(errors.append)
    worker.speech_recognized.connect(results.append)
    worker.run()
    assert not results
    assert 'No clear speech' in errors[0]


def test_voice_low_confidence_does_not_execute(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    transcribe.return_value = ''
    results, errors = [], []
    worker.speech_recognized.connect(results.append)
    worker.error_occurred.connect(errors.append)
    worker.run()
    assert not results and 'clearly' in errors[0]


def test_voice_cancel_before_microphone(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    worker.cancel()
    results = []
    worker.speech_recognized.connect(results.append)
    worker.run()
    worker._get_microphone.assert_not_called()
    assert not results


def test_voice_microphone_failure_still_stops(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    source.__enter__.side_effect = OSError('No microphone')
    with qtbot.waitSignal(worker.listening_stopped):
        with qtbot.waitSignal(worker.error_occurred) as error:
            worker.run()
    assert 'microphone' in error.args[0]


def test_actual_pcm_levels_are_zero_for_silence_and_react_to_audio():
    from array import array
    from src.services.voice_input import audio_level
    assert audio_level(bytes(2048)) == 0
    quiet = audio_level(array('h', [1000, -1000] * 512).tobytes())
    loud = audio_level(array('h', [10000, -10000] * 512).tobytes())
    assert 0 < quiet < loud <= 1


def test_recording_limit_does_not_submit_an_incomplete_command(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    worker.phrase_time_limit = 0.001
    endpoint.feed.return_value = False
    results, errors = [], []
    worker.speech_recognized.connect(results.append)
    worker.error_occurred.connect(errors.append)
    worker.run()
    assert not results
    assert 'recording limit' in errors[0]
    transcribe.assert_not_called()


def test_hold_release_preserves_segments(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    worker.hold_to_talk = True
    worker.timeout = 0.001
    transcribe.return_value = 'open chrome please'
    reads = []
    def read(size):
        reads.append(size)
        if len(reads) == 3:
            worker.finish_recording()
        return bytes(2048)
    source.stream.read.side_effect = read
    results = []
    worker.speech_recognized.connect(results.append)
    worker.run()
    assert results == ['open chrome please']
    assert len(reads) == 3


def test_hold_release_during_warmup_never_opens_microphone(qtbot, streaming_worker, monkeypatch):
    worker, transcribe, source, endpoint = streaming_worker
    worker.hold_to_talk = True
    monkeypatch.setattr('src.services.voice_input.get_multilingual_model', worker.finish_recording)
    worker.run()
    worker._get_microphone.assert_not_called()


@pytest.mark.parametrize('cancel', [False, True])
def test_hold_empty_or_cancelled_does_not_submit(qtbot, streaming_worker, cancel):
    worker, transcribe, source, endpoint = streaming_worker
    worker.hold_to_talk = True
    transcribe.return_value = ''
    def read(size):
        worker.cancel() if cancel else worker.finish_recording()
        return bytes(2048)
    source.stream.read.side_effect = read
    results = []
    worker.speech_recognized.connect(results.append)
    worker.run()
    assert not results


def test_hold_duration_limit_does_not_submit(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    worker.hold_to_talk = True
    worker.phrase_time_limit = 0.001
    errors, results = [], []
    worker.error_occurred.connect(errors.append)
    worker.speech_recognized.connect(results.append)
    worker.run()
    assert 'recording limit' in errors[0]
    assert not results


def test_hold_low_confidence_does_not_submit(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    worker.hold_to_talk = True
    transcribe.return_value = ''
    source.stream.read.side_effect = lambda size: (worker.finish_recording() or bytes(2048))
    results, errors = [], []
    worker.speech_recognized.connect(results.append)
    worker.error_occurred.connect(errors.append)
    worker.run()
    assert not results and 'clearly' in errors[0]


def test_multilingual_hold_ignores_silence_and_finishes_on_release(qtbot, streaming_worker):
    worker, transcribe, source, endpoint = streaming_worker
    worker.hold_to_talk = True
    worker.timeout = 0.001
    worker.mode = 'multilingual'
    transcribe.return_value = 'open chrome'
    reads = []
    def read(size):
        reads.append(size)
        if len(reads) == 3:
            worker.finish_recording()
        return bytes(2048)
    source.stream.read.side_effect = read
    results = []
    worker.speech_recognized.connect(results.append)
    worker.run()
    assert results == ['open chrome']
    assert len(transcribe.call_args.args[0]) == 6144
    assert len(reads) == 3
