"""Local speech recognition with sounddevice capture and cancellable Qt workers.

Multilingual Whisper handles Tamil/English speech after a language-independent
silence detector. The optional English Vosk engine streams partial words.
Models are bundled; runtime never downloads models or uploads microphone audio.
"""
import queue as _queue
import json
import math
import sys
import threading
from array import array
from PyQt6.QtCore import QThread, pyqtSignal
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("voice_input")

# Guard import: SpeechRecognition must be installed
try:
    import speech_recognition as sr

    _SR_AVAILABLE = True
except ImportError:
    sr = None  # type: ignore[assignment]
    _SR_AVAILABLE = False
    logger.warning("SpeechRecognition library not installed. Voice input disabled.")

# Guard import: sounddevice is the preferred audio backend (no C compilation needed)
try:
    import sounddevice as sd

    _SD_AVAILABLE = True
except ImportError:
    sd = None  # type: ignore[assignment]
    _SD_AVAILABLE = False
    if _SR_AVAILABLE:
        logger.warning("sounddevice not installed. Voice input disabled.")

# Runtime never downloads a model: always load the bundled local directory.
try:
    import vosk
    vosk.SetLogLevel(-1)
    _VOSK_AVAILABLE = True
except (ImportError, OSError):
    vosk = None
    _VOSK_AVAILABLE = False

try:
    import numpy as np
    import webrtcvad
    from faster_whisper import WhisperModel
    _MULTILINGUAL_AVAILABLE = True
except (ImportError, OSError):
    np = webrtcvad = WhisperModel = None
    _MULTILINGUAL_AVAILABLE = False

SPEECH_AVAILABLE = _SR_AVAILABLE and _SD_AVAILABLE and (
    (_MULTILINGUAL_AVAILABLE and settings.VOICE_MULTILINGUAL_MODEL_DIR.is_dir())
    if settings.VOICE_MULTILINGUAL else (_VOSK_AVAILABLE and settings.VOICE_MODEL_DIR.is_dir()))
_multilingual_model = None
_multilingual_lock = threading.Lock()
_model = None
_model_lock = threading.Lock()


def get_voice_model():
    global _model
    with _model_lock:
        if _model is None:
            if not settings.VOICE_MODEL_DIR.is_dir():
                raise OSError('Bundled offline speech model is missing.')
            _model = vosk.Model(str(settings.VOICE_MODEL_DIR))
    return _model


def create_recognizer(sample_rate=16000):
    recognizer = vosk.KaldiRecognizer(get_voice_model(), sample_rate)
    recognizer.SetWords(True)
    return recognizer


def get_multilingual_model():
    """Load only verified local model files, including inside a frozen release."""
    global _multilingual_model
    with _multilingual_lock:
        if _multilingual_model is None:
            model_path = settings.VOICE_MULTILINGUAL_MODEL_DIR
            if not (model_path / 'model.bin').is_file():
                raise OSError('Bundled multilingual speech model is missing.')
            _multilingual_model = WhisperModel(str(model_path), device='cpu',
                                               compute_type='int8', cpu_threads=4,
                                               local_files_only=True)
    return _multilingual_model


def resample_pcm(data, sample_rate):
    """Convert mono PCM16 into 16 kHz samples without external executables."""
    samples = np.frombuffer(data, dtype='<i2')
    if sample_rate == 16000:
        return samples
    count = round(len(samples) * 16000 / sample_rate)
    if not count:
        return np.empty(0, dtype='<i2')
    return np.interp(np.arange(count) * sample_rate / 16000,
                     np.arange(len(samples)), samples).astype('<i2')


class SpeechEndpoint:
    """VAD counts complete 20 ms frames; a one-second gap cannot submit speech."""
    def __init__(self, silence_seconds=1.5):
        self.vad = webrtcvad.Vad(2)
        self.silence_frames = math.ceil(max(1.5, silence_seconds) / .02)
        self.pending = bytearray()
        self.started = False
        self.voiced_frames = 0
        self.quiet_frames = 0

    def feed(self, data, sample_rate):
        self.pending.extend(resample_pcm(data, sample_rate).tobytes())
        while len(self.pending) >= 640:
            frame = bytes(self.pending[:640])
            del self.pending[:640]
            if self.vad.is_speech(frame, 16000):
                self.voiced_frames += 1
                self.quiet_frames = 0
                if self.voiced_frames >= 3:
                    self.started = True
            else:
                self.voiced_frames = 0
                if self.started:
                    self.quiet_frames += 1
                    if self.quiet_frames >= self.silence_frames:
                        return True
        return False


def transcribe_multilingual(data, sample_rate, cancelled=lambda: False):
    if cancelled():
        raise InterruptedError()
    audio = resample_pcm(data, sample_rate).astype(np.float32) / 32768
    segments, _ = get_multilingual_model().transcribe(
        audio, language=None, task='transcribe', beam_size=5, temperature=0,
        condition_on_previous_text=False, vad_filter=False,
        initial_prompt='Chrome, Google, YouTube, Notepad, Shape of You. '
                       'தமிழ் மற்றும் English கலந்து பேசும் commands: open பண்ணு, play பண்ணு, பாட்டு போடு, தேடு.')
    words = []
    for segment in segments:
        if cancelled():
            raise InterruptedError()
        # Never turn uncertain/no-speech output into an operating-system action.
        if segment.no_speech_prob > .6 or segment.avg_logprob < -1.0:
            return ''
        words.append(segment.text.strip())
    if cancelled():
        raise InterruptedError()
    return ' '.join(words).strip()


def audio_level(data):
    """RMS meter from actual little-endian mono PCM16 samples, scaled to 0..1."""
    samples = array('h')
    samples.frombytes(data[:len(data) // 2 * 2])
    if sys.byteorder != 'little':
        samples.byteswap()
    if not samples:
        return 0.0
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768
    if rms < 0.001:
        return 0.0
    return max(0.0, min(1.0, (20 * math.log10(rms) + 60) / 54))


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
        level_callback=None,
        cancelled=None,
    ):
        self.device_index = device_index
        self.level_callback = level_callback
        self.cancelled = cancelled or (lambda: False)
        self.SAMPLE_RATE = sample_rate
        self.SAMPLE_WIDTH = 2  # 16-bit PCM: 2 bytes per sample
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
            self.CHUNK = round(self.SAMPLE_RATE * .02)
            self._raw_stream = sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.CHUNK,
                device=self.device_index,
                dtype="int16",
                channels=1,
                callback=_audio_callback,
            )

        try:
            self._raw_stream.start()
        except Exception:
            self._raw_stream.close()
            self._raw_stream = None
            self._queue = None
            raise
        # Recognizer calls source.stream.read(source.CHUNK)
        self.stream = self
        return self

    def read(self, size: int) -> bytes:
        """Reads audio chunk from the queue. Blocks until data arrives."""
        if self._queue is None:
            return b""
        if self.cancelled():
            raise InterruptedError()
        try:
            data = self._queue.get(timeout=2)
            if self.cancelled():
                raise InterruptedError()
            if self.level_callback:
                self.level_callback(audio_level(data))
            return data
        except _queue.Empty:
            raise OSError('Microphone stopped delivering audio.')

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
    """One cancellable utterance; streams PCM and partial text without calibration loss."""
    speech_recognized = pyqtSignal(str)
    partial_recognized = pyqtSignal(str)
    audio_level_changed = pyqtSignal(float)
    processing_started = pyqtSignal()
    error_occurred = pyqtSignal(str)
    listening_started = pyqtSignal()
    listening_stopped = pyqtSignal()

    def __init__(self, timeout=None, phrase_time_limit=None, parent=None):
        super().__init__(parent)
        self._cancel_event = threading.Event()
        self.timeout = timeout if timeout is not None else settings.VOICE_TIMEOUT_S
        self.phrase_time_limit = phrase_time_limit if phrase_time_limit is not None else settings.VOICE_PHRASE_LIMIT_S

    def cancel(self):
        self._cancel_event.set()
        self.requestInterruption()

    def _is_cancelled(self):
        return self._cancel_event.is_set() or self.isInterruptionRequested()

    def _get_microphone(self):
        return SoundDeviceMicrophone(device_index=settings.VOICE_DEVICE_INDEX, chunk_size=320,
                                     level_callback=self.audio_level_changed.emit,
                                     cancelled=self._is_cancelled)

    def _run_multilingual(self):
        get_multilingual_model()  # Finish model warmup before opening the microphone.
        if self._is_cancelled():
            return
        chunks = []
        endpoint = SpeechEndpoint(settings.VOICE_SILENCE_S)
        with self._get_microphone() as source:
            self.listening_started.emit()
            elapsed = 0.0
            speech_start = None
            while not self._is_cancelled():
                data = source.stream.read(source.CHUNK)
                elapsed += len(data) / (source.SAMPLE_RATE * source.SAMPLE_WIDTH)
                chunks.append(data)
                finished = endpoint.feed(data, source.SAMPLE_RATE)
                if endpoint.started and speech_start is None:
                    speech_start = elapsed
                if speech_start is not None and elapsed - speech_start >= self.phrase_time_limit:
                    self.error_occurred.emit('Voice input reached the recording limit. Please try a shorter command.')
                    return
                if finished:
                    break
                if speech_start is None and elapsed >= self.timeout:
                    self.error_occurred.emit('No clear speech detected. Check your microphone and try again.')
                    return
            if self._is_cancelled():
                return
            sample_rate = source.SAMPLE_RATE
        self.processing_started.emit()
        text = transcribe_multilingual(b''.join(chunks), sample_rate, self._is_cancelled)
        if not text:
            self.error_occurred.emit("Didn't catch that clearly. Please try again.")
        elif not self._is_cancelled():
            self.speech_recognized.emit(text)

    def run(self):
        try:
            if not SPEECH_AVAILABLE:
                self.error_occurred.emit('Local speech recognition is not available. Check the bundled model and microphone dependencies.')
                return
            if settings.VOICE_MULTILINGUAL:
                self._run_multilingual()
                return
            # Warm up the model before opening the microphone. No spoken prefix is discarded.
            get_voice_model()
            if self._is_cancelled():
                return
            with self._get_microphone() as source:
                recognizer = create_recognizer(source.SAMPLE_RATE)
                self.listening_started.emit()
                elapsed = 0.0
                speech_start = None
                last_partial = ''
                result = None
                # Audio duration bounds capture even when silence never triggers an endpoint.
                while not self._is_cancelled():
                    data = source.stream.read(source.CHUNK)
                    elapsed += len(data) / (source.SAMPLE_RATE * source.SAMPLE_WIDTH)
                    if recognizer.AcceptWaveform(data):
                        candidate = json.loads(recognizer.Result())
                        if candidate.get('text', '').strip():
                            result = candidate
                            break
                    else:
                        partial = json.loads(recognizer.PartialResult()).get('partial', '')
                        if partial:
                            if speech_start is None:
                                speech_start = elapsed
                            if partial != last_partial:
                                self.partial_recognized.emit(partial)
                                last_partial = partial
                    if speech_start is None and elapsed >= self.timeout:
                        break
                    if speech_start is not None and elapsed - speech_start >= self.phrase_time_limit:
                        self.error_occurred.emit('Voice input reached the recording limit. Please try a shorter command.')
                        return
                if self._is_cancelled():
                    return
                self.processing_started.emit()
                result = result or json.loads(recognizer.FinalResult())
            text = result.get('text', '').strip()
            if not text:
                self.error_occurred.emit('No clear speech detected. Check your microphone and try again.')
                return
            words = result.get('result', [])
            if words and sum(word.get('conf', 0) for word in words) / len(words) < 0.55:
                self.error_occurred.emit("Didn't catch that clearly. Please try again.")
                return
            if not self._is_cancelled():
                self.speech_recognized.emit(text)
        except InterruptedError:
            pass
        except OSError:
            if not self._is_cancelled():
                self.error_occurred.emit('Could not access microphone or local model. Check Windows input settings.')
        except Exception:
            logger.exception('Local voice recognition failed.')
            if not self._is_cancelled():
                self.error_occurred.emit('Local speech recognition failed. Please try again.')
        finally:
            self.audio_level_changed.emit(0.0)
            self.listening_stopped.emit()
