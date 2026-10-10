"""Google integration checks: no microphone hardware or network requests."""
from unittest.mock import MagicMock
import pytest
from src.services import voice_input as voice


@pytest.fixture
def google_worker(monkeypatch):
    monkeypatch.setattr(voice.settings, 'VOICE_MODE', 'google')
    monkeypatch.setattr(voice.settings, 'GOOGLE_VOICE_LANGUAGE', 'en-IN')
    monkeypatch.setattr(voice, 'is_speech_available', lambda mode=None: True)
    endpoint = MagicMock(started=True)
    endpoint.feed.return_value = True
    monkeypatch.setattr(voice, 'SpeechEndpoint', lambda silence: endpoint)
    recognizer = MagicMock()
    recognizer.recognize_google.return_value = 'open chrome'
    monkeypatch.setattr(voice.sr, 'Recognizer', lambda: recognizer)
    monkeypatch.setattr(voice, 'get_multilingual_model', MagicMock(side_effect=AssertionError('Whisper called')))
    source = MagicMock(SAMPLE_RATE=16000, SAMPLE_WIDTH=2, CHUNK=320)
    source.__enter__.return_value = source
    source.stream.read.return_value = bytes(640)
    worker = voice.VoiceInputWorker()
    worker._get_microphone = MagicMock(return_value=source)
    return worker, recognizer, source, endpoint


@pytest.mark.parametrize('language,text', [('en-IN', 'open chrome'), ('ta-IN', 'குரோம் திற')])
def test_google_language_https_timeout_and_signal_order(qtbot, google_worker, language, text):
    worker, recognizer, source, endpoint = google_worker
    worker.google_language = language
    recognizer.recognize_google.return_value = text
    events = []
    worker.listening_started.connect(lambda: events.append('listening'))
    worker.processing_started.connect(lambda: events.append('processing'))
    worker.speech_recognized.connect(events.append)
    worker.listening_stopped.connect(lambda: events.append('stopped'))
    worker.run()
    assert events == ['listening', 'processing', text, 'stopped']
    assert recognizer.operation_timeout == 10
    args, kwargs = recognizer.recognize_google.call_args
    assert args[0].frame_data == bytes(640)
    assert args[0].sample_rate == 16000 and args[0].sample_width == 2
    assert kwargs == dict(language=language, endpoint='https://www.google.com/speech-api/v2/recognize')
    source.__exit__.assert_called_once()


@pytest.mark.parametrize('failure,message', [
    (voice.sr.UnknownValueError(), 'clearly'),
    (voice.sr.RequestError('private service response'), 'internet'),
    (TimeoutError('private timeout'), 'timed out'),
    (RuntimeError('private transcript'), 'failed'),
    (None, 'clearly'),
])
def test_google_failure_never_submits_or_retries(qtbot, google_worker, failure, message, caplog):
    worker, recognizer, source, endpoint = google_worker
    recognizer.recognize_google.side_effect = failure
    recognizer.recognize_google.return_value = '  '
    errors, results, stops = [], [], []
    worker.error_occurred.connect(errors.append)
    worker.speech_recognized.connect(results.append)
    worker.listening_stopped.connect(lambda: stops.append(True))
    worker.run()
    assert not results and message in errors[0] and stops == [True]
    recognizer.recognize_google.assert_called_once()
    assert 'private' not in caplog.text


@pytest.mark.parametrize('during_request', [False, True])
def test_google_cancellation_suppresses_results(qtbot, google_worker, during_request):
    worker, recognizer, source, endpoint = google_worker
    results, errors = [], []
    worker.speech_recognized.connect(results.append)
    worker.error_occurred.connect(errors.append)
    if during_request:
        recognizer.recognize_google.side_effect = lambda *a, **kw: (worker.cancel() or 'open chrome')
    else:
        worker.cancel()
    worker.run()
    assert not results and not errors
    assert recognizer.recognize_google.call_count == int(during_request)


def test_google_silence_never_uploads(qtbot, google_worker):
    worker, recognizer, source, endpoint = google_worker
    endpoint.started = False
    endpoint.feed.return_value = False
    worker.timeout = .04
    errors = []
    worker.error_occurred.connect(errors.append)
    worker.run()
    assert 'No clear speech' in errors[0]
    recognizer.recognize_google.assert_not_called()


@pytest.mark.parametrize('speech', [False, True])
def test_google_hold_release_and_silence(qtbot, google_worker, speech):
    worker, recognizer, source, endpoint = google_worker
    worker.hold_to_talk = True
    endpoint.started = speech
    source.stream.read.side_effect = lambda size: (worker.finish_recording() or bytes(640))
    results = []
    worker.speech_recognized.connect(results.append)
    worker.run()
    assert results == (['open chrome'] if speech else [])
    assert recognizer.recognize_google.call_count == int(speech)


def test_google_limit_never_uploads(qtbot, google_worker):
    worker, recognizer, source, endpoint = google_worker
    worker.hold_to_talk = True
    worker.phrase_time_limit = .01
    errors = []
    worker.error_occurred.connect(errors.append)
    worker.run()
    assert 'recording limit' in errors[0]
    recognizer.recognize_google.assert_not_called()


def test_google_microphone_failure(qtbot, google_worker):
    worker, recognizer, source, endpoint = google_worker
    source.__enter__.side_effect = OSError('private device failure')
    errors = []
    worker.error_occurred.connect(errors.append)
    worker.run()
    assert 'microphone' in errors[0]
    recognizer.recognize_google.assert_not_called()


def test_google_engine_and_language_are_snapshotted(qtbot, google_worker, monkeypatch):
    worker, recognizer, source, endpoint = google_worker
    monkeypatch.setattr(voice.settings, 'VOICE_MODE', 'multilingual')
    monkeypatch.setattr(voice.settings, 'GOOGLE_VOICE_LANGUAGE', 'ta-IN')
    worker.run()
    assert recognizer.recognize_google.call_args.kwargs['language'] == 'en-IN'


def test_google_available_without_local_engines_or_models(monkeypatch, tmp_path):
    # Test the real predicate, not the worker fixture's stub.
    for attr in ('_SR_AVAILABLE', '_SD_AVAILABLE', '_VAD_AVAILABLE'):
        monkeypatch.setattr(voice, attr, True)
    monkeypatch.setattr(voice, '_MULTILINGUAL_AVAILABLE', False)
    monkeypatch.setattr(voice.settings, 'VOICE_MULTILINGUAL_MODEL_DIR', tmp_path / 'missing-whisper')
    assert voice.is_speech_available('google')
    assert not voice.is_speech_available('english')
    assert not voice.is_speech_available('multilingual')
    assert not voice.is_speech_available('invalid')


def test_local_modes_never_call_google(qtbot, monkeypatch):
    google = MagicMock(side_effect=AssertionError('unexpected upload'))
    monkeypatch.setattr(voice.sr.Recognizer, 'recognize_google', google)
    monkeypatch.setattr(voice, 'is_speech_available', lambda mode=None: True)
    for mode, method in [('multilingual', 'get_multilingual_model')]:
        monkeypatch.setattr(voice.settings, 'VOICE_MODE', mode)
        worker = voice.VoiceInputWorker()
        monkeypatch.setattr(voice, method, worker.finish_recording)
        worker.run()
    google.assert_not_called()


def test_windows_flac_encoder_produces_flac_without_network():
    from pathlib import Path
    encoder = Path(voice.sr.__file__).parent / 'flac-win32.exe'
    assert encoder.is_file()
    assert voice.sr.AudioData(bytes(32000), 16000, 2).get_flac_data().startswith(b'fLaC')
