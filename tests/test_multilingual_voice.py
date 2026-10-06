"""Tamil/English voice commands and real offline endpoint/decoder regressions."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import wave
import numpy as np
import pytest
from src.core.application import ApplicationCore
from src.services import voice_input as voice


@pytest.mark.parametrize('spoken,expected', [
    ('Shape of You பாட்டு play பண்ணு', 'play shape of you'),
    ('Chrome open பண்ணு', 'open chrome'),
    ('Play. Shape of You.', 'play shape of you'),
    ('குரோம் ஓபன் பண்ணுங்க', 'open chrome'),
    ('Chrome திற', 'open chrome'),
    ('please chrome open pannunga', 'open chrome'),
    ('ஷேப் ஆஃப் யூ பாட்டு போடு', 'play shape of you'),
    ('வாத்தி கம்மிங் பாட்டு போடு', 'play வாத்தி கம்மிங்'),
    ('play வாத்தி கம்மிங் பாட்டு', 'play வாத்தி கம்மிங்'),
    ('Shape of You paattu play pannu', 'play shape of you'),
    ('சென்னை weather search பண்ணு', 'search சென்னை weather'),
    ('சென்னை வானிலை தேடு', 'search சென்னை வானிலை'),
    ('யூடியூப்-ல வாத்தி கம்மிங் பாட்டு போடு', 'play வாத்தி கம்மிங்'),
    ('யூடியூப் ஓபன் பண்ணு.', 'open youtube'),
])
def test_mixed_voice_routes_to_existing_actions(tmp_path, spoken, expected):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened application')
    launcher.open_registered_url.return_value = (True, 'Opened website')
    core = ApplicationCore(tmp_path, launcher)
    try:
        canonical = core.resolve_voice_phrase(spoken)
        assert canonical == expected
        result = core.execute(canonical, defer_browser=True)
        assert result['success']
        if expected.startswith('play '):
            assert result['browser_action'] == 'music'
            assert result['browser_target'] == expected[5:]
        elif expected.startswith('search '):
            assert result['browser_action'] == 'search'
            assert result['browser_target'] == expected[7:]
    finally:
        core.close()


def test_disabled_and_custom_phrase_precedence(tmp_path):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened application')
    launcher.open_registered_url.return_value = (True, 'Opened website')
    core = ApplicationCore(tmp_path, launcher)
    try:
        chrome = next(c for c in core.commands() if c['target'] == 'chrome')
        core.save_command(chrome['name'], 'application', 'chrome', chrome['phrases'], False, chrome['id'])
        assert not core.execute(core.resolve_voice_phrase('Chrome open பண்ணு'))['success']
        launcher.open_application.assert_not_called()
        core.save_command('Tamil shortcut', 'application', 'notepad', ['Chrome open பண்ணு'])
        assert core.resolve_voice_phrase('Chrome open பண்ணு') == 'Chrome open பண்ணு'
        assert core.execute(core.resolve_voice_phrase('Chrome open பண்ணு'))['success']
        launcher.open_application.assert_called_once_with('notepad')
    finally:
        core.close()


def test_unknown_tamil_action_is_unsupported_and_private(tmp_path):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened application')
    launcher.open_registered_url.return_value = (True, 'Opened website')
    core = ApplicationCore(tmp_path, launcher)
    try:
        assert not core.execute(core.resolve_voice_phrase('எனது secret delete பண்ணு'))['success']
        assert core.history()[0]['trigger_phrase'] == '[unsupported command]'
        launcher.open_application.assert_not_called()
    finally:
        core.close()


def paused_audio():
    with wave.open(str(Path(__file__).parent / 'fixtures/play-pause-shape-of-you.wav'), 'rb') as audio:
        return audio.readframes(audio.getnframes()), audio.getframerate()


@pytest.mark.parametrize('rate', [16000, 44100])
def test_native_language_independent_endpoint_waits_for_complete_speech(rate):
    pcm, source_rate = paused_audio()
    samples = np.frombuffer(pcm, dtype='<i2')
    if rate != source_rate:
        samples = np.interp(np.arange(round(len(samples) * rate / source_rate)) * source_rate / rate,
                            np.arange(len(samples)), samples).astype('<i2')
    speech = samples.tobytes()
    data = speech + bytes(rate * 4)
    frame_bytes = round(rate * .02) * 2
    endpoint = voice.SpeechEndpoint()
    finishes = []
    for offset in range(0, len(data) - frame_bytes + 1, frame_bytes):
        if endpoint.feed(data[offset:offset + frame_bytes], rate):
            finishes.append((offset + frame_bytes) / (rate * 2))
            break
    assert endpoint.started
    assert len(finishes) == 1
    assert finishes[0] >= len(speech) / (rate * 2) + 1.5


def test_multilingual_model_is_local_only(monkeypatch):
    monkeypatch.setattr(voice, '_multilingual_model', None)
    constructor = MagicMock()
    monkeypatch.setattr(voice, 'WhisperModel', constructor)
    voice.get_multilingual_model()
    constructor.assert_called_once_with(str(voice.settings.VOICE_MULTILINGUAL_MODEL_DIR),
                                        device='cpu', compute_type='int8', cpu_threads=4,
                                        local_files_only=True)


def test_decoder_keeps_tamil_and_english_without_translation(monkeypatch):
    model = MagicMock()
    segment = SimpleNamespace(text='Shape of You பாட்டு play பண்ணு', no_speech_prob=.05, avg_logprob=-.1)
    model.transcribe.return_value = (iter([segment]), object())
    monkeypatch.setattr(voice, 'get_multilingual_model', lambda: model)
    assert voice.transcribe_multilingual(bytes(640), 16000) == segment.text
    assert model.transcribe.call_args.kwargs['task'] == 'transcribe'
    assert model.transcribe.call_args.kwargs['language'] is None
    model.transcribe.return_value = (iter([SimpleNamespace(text='hallucination', no_speech_prob=.95, avg_logprob=-.1)]), object())
    assert voice.transcribe_multilingual(bytes(640), 16000) == ''
    with pytest.raises(InterruptedError):
        voice.transcribe_multilingual(bytes(640), 16000, lambda: True)


@pytest.fixture
def mixed_worker(monkeypatch):
    monkeypatch.setattr(voice.settings, 'VOICE_MODE', 'multilingual')
    monkeypatch.setattr(voice, 'is_speech_available', lambda mode=None: True)
    monkeypatch.setattr(voice, 'get_multilingual_model', lambda: object())
    transcriber = MagicMock(return_value='Shape of You பாட்டு play பண்ணு')
    monkeypatch.setattr(voice, 'transcribe_multilingual', transcriber)
    pcm, rate = paused_audio()
    assert rate == 16000
    pcm += bytes(rate * 4)
    chunks = [pcm[i:i + 640] for i in range(0, len(pcm), 640)]
    source = MagicMock(SAMPLE_RATE=rate, SAMPLE_WIDTH=2, CHUNK=320)
    source.__enter__.return_value = source
    source.stream.read.side_effect = chunks
    worker = voice.VoiceInputWorker()
    worker._get_microphone = MagicMock(return_value=source)
    return worker, source, transcriber


def test_mixed_worker_submits_once_after_final_silence(qtbot, mixed_worker):
    worker, source, transcriber = mixed_worker
    events = []
    worker.listening_started.connect(lambda: events.append('listening'))
    worker.processing_started.connect(lambda: events.append('processing'))
    worker.speech_recognized.connect(events.append)
    worker.listening_stopped.connect(lambda: events.append('stopped'))
    worker.run()
    assert events == ['listening', 'processing', 'Shape of You பாட்டு play பண்ணு', 'stopped']
    pcm, rate = paused_audio()
    assert source.stream.read.call_count * .02 >= len(pcm) / (rate * 2) + 1.5
    transcriber.assert_called_once()
    source.__exit__.assert_called_once()


def test_mixed_worker_limit_and_cancel_never_decode(qtbot, mixed_worker):
    worker, source, transcriber = mixed_worker
    worker.phrase_time_limit = .1
    errors, results = [], []
    worker.error_occurred.connect(errors.append)
    worker.speech_recognized.connect(results.append)
    worker.run()
    assert not results and 'recording limit' in errors[0]
    transcriber.assert_not_called()
    worker.cancel()
    worker._get_microphone.reset_mock()
    worker.run()
    worker._get_microphone.assert_not_called()


def test_mixed_worker_silence_never_decode(qtbot, mixed_worker):
    worker, source, transcriber = mixed_worker
    source.stream.read.side_effect = None
    source.stream.read.return_value = bytes(640)
    worker.timeout = .1
    errors = []
    worker.error_occurred.connect(errors.append)
    worker.run()
    assert 'No clear speech' in errors[0]
    transcriber.assert_not_called()


def test_real_multilingual_decoder_retains_english_command():
    if not voice.is_speech_available('multilingual'):
        pytest.skip('Prepare the offline multilingual model first.')
    pcm, rate = paused_audio()
    assert voice.get_multilingual_model().model.is_multilingual
    result = voice.transcribe_multilingual(pcm + bytes(rate * 3), rate)
    from src.commands.voice_phrases import normalize_mixed_voice
    core_phrase = normalize_mixed_voice(result)
    assert core_phrase == 'play shape of you'


def test_real_multilingual_decoder_transcribes_tamil_without_translation():
    if not voice.is_speech_available('multilingual'):
        pytest.skip('Prepare the offline multilingual model first.')
    with wave.open(str(Path(__file__).parent / 'fixtures/tamil-fleurs.wav'), 'rb') as audio:
        pcm = audio.readframes(audio.getnframes())
        rate = audio.getframerate()
    text = voice.transcribe_multilingual(pcm, rate)
    assert 'நீங்கள்' in text and 'இது' in text
    assert sum('\u0b80' <= char <= '\u0bff' for char in text) > 60
