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
# VoiceInputWorker tests (mocked — no hardware)
# ---------------------------------------------------------------------------

class TestVoiceInputWorkerUnavailable:
    """Test worker behavior when SpeechRecognition is not available."""

    @patch("src.services.voice_input.SPEECH_AVAILABLE", False)
    def test_emits_error_when_unavailable(self, qtbot):
        from src.services.voice_input import VoiceInputWorker

        worker = VoiceInputWorker()
        worker._recognizer = None

        errors = []
        stopped = []
        worker.error_occurred.connect(lambda msg: errors.append(msg))
        worker.listening_stopped.connect(lambda: stopped.append(True))

        worker.run()

        assert len(errors) == 1
        assert "not available" in errors[0].lower()
        assert len(stopped) == 1


class TestVoiceInputWorkerRecognition:
    """Test worker transcription with mocked SpeechRecognition."""

    def test_emits_recognized_text_on_success(self, qtbot):
        """Worker should emit speech_recognized with the transcribed text."""
        from src.services.voice_input import VoiceInputWorker

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.return_value = "open chrome"
        mock_recognizer.adjust_for_ambient_noise = MagicMock()

        worker = VoiceInputWorker()
        worker._recognizer = mock_recognizer

        # Mock _get_microphone to return a dummy context manager
        mock_source = MagicMock()
        mock_source.__enter__ = MagicMock(return_value=mock_source)
        mock_source.__exit__ = MagicMock(return_value=False)
        worker._get_microphone = MagicMock(return_value=mock_source)

        results = []
        stopped = []
        worker.speech_recognized.connect(lambda text: results.append(text))
        worker.listening_stopped.connect(lambda: stopped.append(True))

        worker.run()

        assert results == ["open chrome"]
        assert len(stopped) == 1

    def test_emits_error_on_wait_timeout(self, qtbot):
        """Worker should emit error_occurred when no speech is detected within timeout."""
        from src.services.voice_input import VoiceInputWorker
        import speech_recognition as sr_lib

        mock_recognizer = MagicMock()
        mock_recognizer.listen.side_effect = sr_lib.WaitTimeoutError("timeout")
        mock_recognizer.adjust_for_ambient_noise = MagicMock()

        worker = VoiceInputWorker()
        worker._recognizer = mock_recognizer

        mock_source = MagicMock()
        mock_source.__enter__ = MagicMock(return_value=mock_source)
        mock_source.__exit__ = MagicMock(return_value=False)
        worker._get_microphone = MagicMock(return_value=mock_source)

        errors = []
        recognized = []
        worker.error_occurred.connect(lambda msg: errors.append(msg))
        worker.speech_recognized.connect(lambda text: recognized.append(text))

        worker.run()

        assert len(errors) == 1
        assert "no speech" in errors[0].lower()
        assert len(recognized) == 0

    def test_emits_error_on_unknown_value(self, qtbot):
        """Worker should emit error_occurred when speech is not understood."""
        from src.services.voice_input import VoiceInputWorker
        import speech_recognition as sr_lib

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.side_effect = sr_lib.UnknownValueError()
        mock_recognizer.adjust_for_ambient_noise = MagicMock()

        worker = VoiceInputWorker()
        worker._recognizer = mock_recognizer

        mock_source = MagicMock()
        mock_source.__enter__ = MagicMock(return_value=mock_source)
        mock_source.__exit__ = MagicMock(return_value=False)
        worker._get_microphone = MagicMock(return_value=mock_source)

        errors = []
        worker.error_occurred.connect(lambda msg: errors.append(msg))

        worker.run()

        assert len(errors) == 1
        assert "catch" in errors[0].lower() or "try again" in errors[0].lower()

    def test_emits_error_on_request_error(self, qtbot):
        """Worker should handle network/service errors gracefully."""
        from src.services.voice_input import VoiceInputWorker
        import speech_recognition as sr_lib

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.side_effect = sr_lib.RequestError("Network error")
        mock_recognizer.adjust_for_ambient_noise = MagicMock()

        worker = VoiceInputWorker()
        worker._recognizer = mock_recognizer

        mock_source = MagicMock()
        mock_source.__enter__ = MagicMock(return_value=mock_source)
        mock_source.__exit__ = MagicMock(return_value=False)
        worker._get_microphone = MagicMock(return_value=mock_source)

        errors = []
        worker.error_occurred.connect(lambda msg: errors.append(msg))

        worker.run()

        assert len(errors) == 1
        assert "service unavailable" in errors[0].lower() or "internet" in errors[0].lower()

    def test_emits_error_on_microphone_os_error(self, qtbot):
        """Worker should handle microphone access failures gracefully."""
        from src.services.voice_input import VoiceInputWorker

        mock_source = MagicMock()
        mock_source.__enter__ = MagicMock(
            side_effect=OSError("No default input device")
        )
        mock_source.__exit__ = MagicMock(return_value=False)

        worker = VoiceInputWorker()
        worker._recognizer = MagicMock()
        worker._get_microphone = MagicMock(return_value=mock_source)

        errors = []
        worker.error_occurred.connect(lambda msg: errors.append(msg))

        worker.run()

        assert len(errors) == 1
        assert "microphone" in errors[0].lower()


class TestVoiceInputWorkerSignalContract:
    """Verify that listening_stopped is always emitted (success or failure)."""

    def test_listening_stopped_always_emitted_on_success(self, qtbot):
        from src.services.voice_input import VoiceInputWorker

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.return_value = "hello"
        mock_recognizer.adjust_for_ambient_noise = MagicMock()

        mock_source = MagicMock()
        mock_source.__enter__ = MagicMock(return_value=mock_source)
        mock_source.__exit__ = MagicMock(return_value=False)

        worker = VoiceInputWorker()
        worker._recognizer = mock_recognizer
        worker._get_microphone = MagicMock(return_value=mock_source)

        stopped = []
        worker.listening_stopped.connect(lambda: stopped.append(True))
        worker.run()
        assert len(stopped) == 1

    def test_listening_stopped_always_emitted_on_error(self, qtbot):
        from src.services.voice_input import VoiceInputWorker

        mock_source = MagicMock()
        mock_source.__enter__ = MagicMock(
            side_effect=OSError("fail")
        )
        mock_source.__exit__ = MagicMock(return_value=False)

        worker = VoiceInputWorker()
        worker._recognizer = MagicMock()
        worker._get_microphone = MagicMock(return_value=mock_source)

        stopped = []
        worker.listening_stopped.connect(lambda: stopped.append(True))
        worker.run()
        assert len(stopped) == 1
