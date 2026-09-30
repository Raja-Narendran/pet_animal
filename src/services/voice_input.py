"""Speech-to-text service using SpeechRecognition with sounddevice microphone capture.

Runs recognition in a background QThread so the UI stays responsive while the
blocking ``sr.Recognizer.listen()`` call executes. All results are delivered
back to the main thread via Qt signals.

Microphone capture:
    Uses ``sounddevice`` for microphone capture (bundled PortAudio binary,
    full Python 3.14+ compatibility). The ``SoundDeviceMicrophone`` class
    implements the ``speech_recognition.AudioSource`` protocol.

Speech Recognition Engine:
    Uses Google Web Speech API (built-in default key in ``SpeechRecognition``).
    - 100% Free of charge.
    - Zero setup / accounts / API keys required.
    - High accuracy for desktop commands.
"""
import queue as _queue
import sys
from PyQt6.QtCore import QThread, pyqtSignal
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("voice_input")

# Guard import — SpeechRecognition must be installed
try:
    import speech_recognition as sr

    _SR_AVAILABLE = True
except ImportError:
    sr = None  # type: ignore[assignment]
    _SR_AVAILABLE = False
    logger.warning("SpeechRecognition library not installed. Voice input disabled.")

# Guard import — sounddevice is the preferred audio backend (no C compilation needed)
try:
    import sounddevice as sd

    _SD_AVAILABLE = True
except ImportError:
    sd = None  # type: ignore[assignment]
    _SD_AVAILABLE = False
    if _SR_AVAILABLE:
        logger.warning("sounddevice not installed. Voice input disabled.")

# Try PyAudio as fallback
_PYAUDIO_AVAILABLE = False
if _SR_AVAILABLE and not _SD_AVAILABLE:
    try:
        import pyaudio  # noqa: F401

        _PYAUDIO_AVAILABLE = True
    except ImportError:
        pass

# Voice input is available if we have SR + at least one audio capture backend
SPEECH_AVAILABLE = _SR_AVAILABLE and (_SD_AVAILABLE or _PYAUDIO_AVAILABLE)

if not SPEECH_AVAILABLE and _SR_AVAILABLE:
    logger.warning(
        "No audio backend available (install sounddevice or pyaudio). "
        "Voice input disabled."
    )


# ---------------------------------------------------------------------------
# SoundDevice-based Microphone (AudioSource protocol for SpeechRecognition)
# ---------------------------------------------------------------------------


class SoundDeviceMicrophone(sr.AudioSource if _SR_AVAILABLE else object):
    """Microphone audio source using ``sounddevice``.

    Implements the ``speech_recognition.AudioSource`` context-manager protocol
    so it plugs directly into ``sr.Recognizer().listen(source)``.
    """

    def __init__(
        self,
        device_index: int | None = None,
        sample_rate: int = 16_000,
        chunk_size: int = 1024,
    ):
        self.device_index = device_index
        self.SAMPLE_RATE = sample_rate
        self.SAMPLE_WIDTH = 2  # 16-bit PCM → 2 bytes per sample
        self.CHUNK = chunk_size

        self._raw_stream = None
        self._queue: _queue.Queue | None = None
        self.stream = None

    # --- context-manager protocol expected by sr.Recognizer.listen() ---

    def __enter__(self):
        self._queue = _queue.Queue()

        def _audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug(f"sounddevice status: {status}")
            if self._queue is not None:
                self._queue.put(bytes(indata))

        try:
            self._raw_stream = sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.CHUNK,
                device=self.device_index,
                dtype="int16",
                channels=1,
                callback=_audio_callback,
            )
        except Exception:
            # Fallback to device's default sample rate if 16000 is unsupported
            dev_info = sd.query_devices(self.device_index, kind="input")
            self.SAMPLE_RATE = int(dev_info["default_samplerate"])
            self._raw_stream = sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.CHUNK,
                device=self.device_index,
                dtype="int16",
                channels=1,
                callback=_audio_callback,
            )

        self._raw_stream.start()
        # Recognizer calls source.stream.read(source.CHUNK)
        self.stream = self
        return self

    def read(self, size: int) -> bytes:
        """Reads audio chunk from the queue. Blocks until data arrives."""
        if self._queue is None:
            return b""
        return self._queue.get()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._raw_stream is not None:
            try:
                self._raw_stream.stop()
                self._raw_stream.close()
            except Exception as e:
                logger.debug(f"Error stopping stream: {e}")
            self._raw_stream = None
        self.stream = None
        self._queue = None


# ---------------------------------------------------------------------------
# VoiceInputWorker
# ---------------------------------------------------------------------------


class VoiceInputWorker(QThread):
    """Background thread that captures microphone audio and runs STT.

    Signals:
        speech_recognized(str): Emitted with transcribed text on success.
        error_occurred(str): Emitted with user-friendly error message on failure.
        listening_started(): Emitted when microphone capture begins.
        listening_stopped(): Emitted when recognition completes (success or failure).
    """

    speech_recognized = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    listening_started = pyqtSignal()
    listening_stopped = pyqtSignal()

    def __init__(
        self,
        timeout: int | None = None,
        phrase_time_limit: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.timeout = timeout if timeout is not None else settings.VOICE_TIMEOUT_S
        self.phrase_time_limit = (
            phrase_time_limit
            if phrase_time_limit is not None
            else settings.VOICE_PHRASE_LIMIT_S
        )
        self._recognizer = sr.Recognizer() if _SR_AVAILABLE else None
        if self._recognizer is not None:
            self._recognizer.operation_timeout = settings.VOICE_NETWORK_TIMEOUT_S

    def _get_microphone(self):
        """Returns the best available microphone source."""
        if _SD_AVAILABLE:
            return SoundDeviceMicrophone()
        else:
            return sr.Microphone()

    def run(self) -> None:
        """Captures audio from the default microphone and transcribes it."""
        if not SPEECH_AVAILABLE or self._recognizer is None:
            self.error_occurred.emit("Speech recognition is not available.")
            self.listening_stopped.emit()
            return

        try:
            with self._get_microphone() as source:
                # Brief ambient noise adjustment (0.5s calibration)
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.listening_started.emit()
                logger.info("Listening for voice command...")

                audio = self._recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )

            # Transcribe using Google Speech Recognition (free, built-in Chromium key, no signup required)
            logger.info("Recognizing speech via Google Speech API...")
            text = self._recognizer.recognize_google(audio)
            text = text.strip()

            if text:
                logger.info(f"Voice recognized: '{text}'")
                self.speech_recognized.emit(text)
            else:
                self.error_occurred.emit("Could not understand. Please try again.")

        except sr.WaitTimeoutError:
            logger.info("Voice input timed out (no speech detected).")
            self.error_occurred.emit("No speech detected. Try again!")
        except sr.UnknownValueError:
            logger.info("Speech not understood.")
            self.error_occurred.emit("Didn't catch that. Please try again.")
        except sr.RequestError as e:
            logger.error(f"Speech recognition network/service error: {e}")
            self.error_occurred.emit("Voice service unavailable (check internet).")
        except OSError as e:
            logger.error(f"Microphone access error: {e}")
            self.error_occurred.emit("Could not access microphone.")
        except Exception as e:
            logger.exception(f"Unexpected voice input error: {e}")
            self.error_occurred.emit(f"Voice error: {e}")
        finally:
            self.listening_stopped.emit()
