"""Conservative normalization and language-aware negation regressions."""
import pytest
from src.commands.interpreter.normalizer import normalize_input
from src.commands.voice_phrases import normalize_mixed_voice


@pytest.mark.parametrize('phrase,expected', [
    ('  OPEN\t  Chrome?!  ', 'open chrome'),
    ('Can you please open Chrome?', 'open chrome'),
    ('Could you launch Chrome for me please?', 'open chrome'),
    ('Please bring up Chrome!', 'bring up chrome'),
    ('Chrome open pannunga', 'open chrome'),
    ('Chrome ah open pannu', 'open chrome ah'),
    ('குரோம் ஓபன் பண்ணுங்க', 'open chrome'),
    ('Chrome திற', 'open chrome'),
    ('vs code start pannu', 'open vs code'),
    ('search please please me', 'search please please me'),
    ('search recipes for me', 'search recipes for me'),
    ('search help please', 'search help please'),
    ('play save the last dance for me', 'play save the last dance for me'),
    ('Can you play please please me', 'play please please me'),
    ("play don't stop me now", "play don't stop me now"),
    ('open chrome; powershell', 'open chrome; powershell'),
])
def test_normalization_preserves_payload_and_operators(phrase, expected):
    result = normalize_input(phrase)
    assert result.valid and not result.negated
    assert result.text == expected


NEGATIVE_PHRASES = [
    "don't open chrome", 'don’t launch chrome', 'do not open chrome',
    'please do not start chrome', 'can you not open chrome', 'never open chrome',
    'chrome open panna vendam', 'chrome open pannathe', 'chrome thira vendaam',
    'வேண்டாம்', 'திறக்க வேண்டாம்', 'குரோம் திறக்காதே',
    "don't search for cats", 'do not play shape of you',
]


@pytest.mark.parametrize('phrase', NEGATIVE_PHRASES)
def test_negation_survives_normalization(phrase):
    assert normalize_input(phrase).negated
    assert normalize_input(normalize_mixed_voice(phrase)).negated


@pytest.mark.parametrize('phrase', [None, 1, 'x' * 501, 'open chrome\x00', 'open chrome\ncmd /c calc', 'open chrome\x1b'])
def test_invalid_inputs_are_rejected(phrase):
    assert not normalize_input(phrase).valid
