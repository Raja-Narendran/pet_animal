"""Structured metadata resolution, state checks, and ambiguity without execution."""
import json
import pytest
from src.commands.interpreter import CommandIntent, IntentType, IntentResolver, MatchReason


def command(identifier='chrome', target='chrome', enabled=True, action='application'):
    return dict(id=identifier, name='Arbitrary name', action_type=action,
                action_config=json.dumps({'target': target}), enabled=enabled,
                phrases=['completely unrelated phrase'])


def test_metadata_wins_over_names_and_phrases():
    result = IntentResolver().resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'chrome'), [command()])
    assert result.matched and result.command_id == 'chrome'


@pytest.mark.parametrize('commands,reason', [
    ([], MatchReason.UNAVAILABLE_COMMAND),
    ([command(enabled=False)], MatchReason.DISABLED_COMMAND),
    ([command(), command('other')], MatchReason.AMBIGUOUS_COMMAND),
    ([command(target='notepad')], MatchReason.UNAVAILABLE_COMMAND),
])
def test_unavailable_disabled_ambiguous_commands(commands, reason):
    result = IntentResolver().resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'chrome'), commands)
    assert not result.matched and result.reason == reason


def test_unique_enabled_registration_and_confidence_gate():
    commands = [command(), command('disabled', enabled=False)]
    assert IntentResolver().resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'chrome'), commands).matched
    low = IntentResolver().resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'chrome', confidence=.8), commands)
    assert low.command_id == 'chrome' and not low.matched and low.reason == MatchReason.LOW_CONFIDENCE
    invalid = IntentResolver().resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'chrome', confidence=float('nan')), commands)
    assert not invalid.matched


@pytest.mark.parametrize('kind,target,url', [
    (IntentType.OPEN_WEBSITE, 'youtube', 'https://www.youtube.com'),
    (IntentType.PLAY_MEDIA, 'youtube', 'https://www.youtube.com'),
    (IntentType.WEB_SEARCH, 'google', 'https://www.google.com'),
])
def test_browser_capabilities_require_registered_website(kind, target, url):
    intent = CommandIntent(kind, target, 'private value')
    resolver = IntentResolver()
    assert resolver.resolve(intent, []).reason == MatchReason.UNAVAILABLE_COMMAND
    assert resolver.resolve(intent, [command(target=url, action='url')]).matched
    assert not resolver.resolve(intent, [command(target=url, enabled=False, action='url')]).matched
