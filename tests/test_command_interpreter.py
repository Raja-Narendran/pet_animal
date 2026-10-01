"""Pure deterministic interpretation: no GUI, database, or launcher required."""
from dataclasses import FrozenInstanceError
import pytest
from src.commands.interpreter import CommandIntent, IntentType, MatchReason, RuleBasedIntentInterpreter
from .test_command_normalizer import NEGATIVE_PHRASES


OPEN_PHRASES = [
    ('open chrome', 'chrome'), ('Can you open Chrome?', 'chrome'),
    ('Please start Chrome', 'chrome'), ('Launch Google Chrome for me', 'chrome'),
    ('Could you bring up Chrome?', 'chrome'), ('I need Chrome', 'chrome'),
    ('Chrome open pannunga', 'chrome'), ('Chrome ah open pannu', 'chrome'),
    ('Open the browser', 'chrome'), ('Start my browser', 'chrome'),
    ('open my browser', 'chrome'), ('குரோம் ஓபன் பண்ணுங்க', 'chrome'),
    ('open vscode', 'vscode'), ('open vs code', 'vscode'),
    ('launch visual studio code', 'vscode'), ('start vscode', 'vscode'),
    ('open my code editor', 'vscode'), ('vs code open pannu', 'vscode'),
    ('vs code start pannu', 'vscode'), ('விஎஸ் கோடு திற', 'vscode'),
    ('open calculator', 'calculator'), ('launch calculator', 'calculator'),
    ('start calculator', 'calculator'), ('open calc', 'calculator'),
    ('calculator open pannu', 'calculator'), ('கணிப்பான் திற', 'calculator'),
    ('open file explorer', 'explorer'), ('launch explorer', 'explorer'),
    ('show file explorer', 'explorer'), ('open explorer', 'explorer'),
    ('open note pad', 'notepad'), ('நோட்பேட் திற', 'notepad'),
]


@pytest.mark.parametrize('phrase,target', OPEN_PHRASES)
def test_application_intents(phrase, target):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.matched and result.command_id is None
    assert result.intent.intent == IntentType.OPEN_APPLICATION
    assert result.intent.target == target
    assert result.confidence >= .85


@pytest.mark.parametrize('phrase,target', [
    ('open youtube', 'youtube'), ('take me to youtube', 'youtube'),
    ('launch youtube', 'youtube'), ('youtube open pannu', 'youtube'),
    ('open google', 'google'), ('go to google', 'google'),
    ('launch google', 'google'), ('google open pannu', 'google'),
    ('யூடியூப் ஓபன் பண்ணு', 'youtube'),
])
def test_website_intents(phrase, target):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.matched
    assert (result.intent.intent, result.intent.target) == (IntentType.OPEN_WEBSITE, target)


@pytest.mark.parametrize('phrase,kind,value', [
    ('search Salesforce DevOps', IntentType.WEB_SEARCH, 'salesforce devops'),
    ('search Google for Salesforce DevOps', IntentType.WEB_SEARCH, 'salesforce devops'),
    ('look up Salesforce deployment best practices', IntentType.WEB_SEARCH, 'salesforce deployment best practices'),
    ('find Salesforce CI/CD', IntentType.WEB_SEARCH, 'salesforce ci/cd'),
    ('Could you search Google for cats?', IntentType.WEB_SEARCH, 'cats'),
    ('சென்னை weather search பண்ணு', IntentType.WEB_SEARCH, 'சென்னை weather'),
    ('play Shape of You', IntentType.PLAY_MEDIA, 'shape of you'),
    ('play Shape of You on YouTube', IntentType.PLAY_MEDIA, 'shape of you'),
    ('can you play Shape of You', IntentType.PLAY_MEDIA, 'shape of you'),
    ('Shape of You song play pannu', IntentType.PLAY_MEDIA, 'shape of you'),
    ('வாத்தி கம்மிங் பாட்டு போடு', IntentType.PLAY_MEDIA, 'வாத்தி கம்மிங்'),
    ("play Don't Stop Me Now", IntentType.PLAY_MEDIA, "don't stop me now"),
    ('play Save the Last Dance for Me', IntentType.PLAY_MEDIA, 'save the last dance for me'),
    ('search help please', IntentType.WEB_SEARCH, 'help please'),
])
def test_free_form_intents_preserve_query_words(phrase, kind, value):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.matched
    assert (result.intent.intent, result.intent.value) == (kind, value)


@pytest.mark.parametrize('phrase', NEGATIVE_PHRASES)
def test_negated_intent_is_rejected(phrase):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert not result.matched and result.reason == MatchReason.NEGATED_COMMAND


@pytest.mark.parametrize('phrase', ['delete chrome', 'remove chrome', 'chrome', 'cmd /c calc',
                                   'powershell open chrome', 'rm -rf /', 'del chrome',
                                   'open chrome & calc', 'open chrome; run notepad', 'open https://example.com'])
def test_no_fuzzy_actions_or_shell_interpretation(phrase):
    assert not RuleBasedIntentInterpreter().interpret(phrase).matched


def test_unknown_target_low_confidence_and_ambiguity():
    interpreter = RuleBasedIntentInterpreter()
    assert interpreter.interpret('open photoshop').reason == MatchReason.UNSUPPORTED_TARGET
    assert interpreter.interpret('open code').confidence < .85
    ambiguous = RuleBasedIntentInterpreter(application_aliases={'chrome': {'browser'}, 'vscode': {'browser'}})
    assert ambiguous.interpret('open browser').reason == MatchReason.AMBIGUOUS_TARGET


@pytest.mark.parametrize('phrase', ['save my name as Naren', 'my name is Naren, remember that', 'remember my name as Naren'])
def test_explicit_memory_store_preserves_case(phrase):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.intent.intent == IntentType.MEMORY_STORE
    assert result.intent.value == 'Naren'


def test_models_are_immutable_and_interface_does_not_execute():
    intent = CommandIntent(IntentType.OPEN_APPLICATION, 'chrome')
    with pytest.raises(FrozenInstanceError):
        intent.target = 'powershell'
    assert intent.source == 'rule_based'
