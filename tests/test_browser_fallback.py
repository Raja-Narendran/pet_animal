"""Browser fallback integration, offline domain grammar and worker privacy."""
import ast
import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from src.app.controller import ApplicationController, BrowserWorker
from src.commands.interpreter import CommandIntent, InterpretationResult, IntentType, MatchReason
from src.commands.interpreter.browser_rules import (
    DIRECT_WEBSITE_SOURCE, website_url, top_level_domains,
)
from src.config.settings import settings
from src.core.application import ApplicationCore
from src.services.windows_launcher import WindowsLauncher


@pytest.fixture
def core(tmp_path):
    launcher = MagicMock()
    for name in ('search_web', 'play_youtube', 'open_registered_url', 'open_application'):
        getattr(launcher, name).return_value = (True, 'Browser action completed.')
    service = ApplicationCore(tmp_path / 'data', launcher)
    yield service
    if not getattr(service, '_closed_by_controller', False):
        service.close()


@pytest.mark.parametrize('phrase', [
    'weather tomorrow', 'Salesforce DevOps?', '  Python + Qt tutorials!  ',
    'amazon.com reviews', 'how to delete a Python dictionary key',
    'example.notarealtld',
])
def test_plain_text_search_preserves_query_and_private_history(core, phrase):
    before = core.db.total_changes
    interpretation = core.interpret(phrase)
    assert interpretation.matched and interpretation.intent.intent == IntentType.WEB_SEARCH
    assert interpretation.intent.value == phrase.strip()
    assert core.db.total_changes == before and not core.launcher.mock_calls
    assert core.execute(phrase)['success']
    core.launcher.search_web.assert_called_once_with(phrase.strip())
    core.launcher.open_registered_url.assert_not_called()
    assert core.history()[0]['trigger_phrase'] == '[web search]'
    assert phrase.strip() not in json.dumps(core.history())


@pytest.mark.parametrize('value,target', [
    ('amazon.com', 'https://amazon.com'),
    ('  AMAZON.COM  ', 'https://amazon.com'),
    ('amazon.co.uk', 'https://amazon.co.uk'),
    ('python.org', 'https://python.org'),
    ('example.in', 'https://example.in'),
    ('example.photography', 'https://example.photography'),
    ('docs.python.org', 'https://docs.python.org'),
    ('bücher.de', 'https://xn--bcher-kva.de'),
    ('例子.中国', 'https://xn--fsqu00a.xn--fiqs8s'),
    ('https://docs.python.org/3/?q=Python#Intro', 'https://docs.python.org/3/?q=Python#Intro'),
    ('HTTPS://AMAZON.COM/', 'https://amazon.com/'),
    ('amazon.com:443', 'https://amazon.com:443'),
    ('https://amazon.com:443/', 'https://amazon.com:443/'),
])
def test_direct_domains_are_validated_and_private(core, value, target):
    interpretation = core.interpret(value)
    assert interpretation.matched and not interpretation.command_id
    assert interpretation.intent.intent == IntentType.OPEN_WEBSITE
    assert interpretation.intent.source == DIRECT_WEBSITE_SOURCE
    assert interpretation.intent.target == target
    assert core.execute(value)['success']
    core.launcher.open_registered_url.assert_called_once_with(target)
    core.launcher.search_web.assert_not_called()
    history = core.history()
    assert history[0]['trigger_phrase'] == '[website open]'
    assert history[0]['name'] == 'Website open'
    assert value.strip() not in json.dumps(history)


@pytest.mark.parametrize('value', [
    'http://example.com', 'ftp://example.com', 'file:///C:/secret',
    'javascript:alert(1)', 'https://user:pass@example.com',
    'https://@example.com', 'https://example.com:444', 'https://example.com:bad',
    'https://example.com:', 'https://example.com./', 'https://example.notarealtld',
    'https://-bad.com', 'https://bad_.com', 'https://bad..com',
    'https://example.com\\evil', 'https://example.com evil',
    'https://example.com\nsecret', 'https://example.com\x7f',
    'https://localhost', 'https://127.0.0.1', '//example.com',
    'C:\\secret.txt', '', '   ', 'a' * 501, '\tamazon.com',
    'https://example.com/' + 'a' * 500,
])
def test_unsafe_or_invalid_explicit_addresses_do_not_launch(core, value):
    assert not core.execute(value, defer_browser=True)['success']
    assert not core.launcher.mock_calls
    assert all(value not in row['error_message'] for row in core.history() if value)


@pytest.mark.parametrize('value', [
    'example.unknownextension', '-bad.com', 'bad-.com', 'bad..com',
    'bad_.com', 'xn--.com', 'a' * 64 + '.com', 'localhost',
    'https://user@example.com', 'https://example.com:444',
    'https://example.com\\evil', 'amazon.com reviews', 'example.com:bad',
])
def test_domain_grammar_rejects_non_addresses(value):
    assert website_url(value) is None


@pytest.mark.parametrize('phrase', [
    'open unknown-app', 'open', 'search', 'search for', 'play', 'remember',
    'save', 'workflow', 'routine', 'locate', 'select', 'cmd /c calc',
    'powershell secret-password', 'delete chrome', 'rm -rf /',
    'please open unknown-app', 'do not open amazon.com',
    '@unknown-app', '/bad*query', 'எனது secret delete பண்ணு',
])
def test_explicit_commands_and_vetoes_do_not_fall_back(core, phrase):
    assert not core.execute(phrase)['success']
    assert not core.launcher.mock_calls


def test_command_memory_and_file_precedence(core):
    core.save_command('Custom', 'application', 'notepad', ['weather tomorrow', 'amazon.com'])
    assert core.execute('weather tomorrow')['success']
    assert core.execute('amazon.com')['success']
    assert core.execute('chrome')['success']
    assert core.launcher.open_application.call_count == 3
    assert not core.launcher.search_web.called and not core.launcher.open_registered_url.called
    record = next(c for c in core.commands() if c['name'] == 'Custom')
    core.save_command('Custom', 'application', 'notepad', record['phrases'], False, record['id'])
    assert core.interpret('amazon.com').reason == MatchReason.DISABLED_COMMAND
    assert not core.execute('amazon.com')['success']
    assert 'confirmation' in core.execute('remember my name as Naren')
    for phrase in ('/report', 'find report', 'open it', 'yes', 'cancel'):
        assert core.interpret(phrase).intent.intent == IntentType.FILE_SEARCH


def test_explicit_search_domain_remains_a_search(core):
    assert core.execute('search amazon.com')['success']
    core.launcher.search_web.assert_called_once_with('amazon.com')
    core.launcher.open_registered_url.assert_not_called()


@pytest.mark.parametrize('deleted', [False, True])
def test_fallback_search_respects_google_registration(core, deleted):
    google = next(c for c in core.commands() if c['target'] == 'https://www.google.com')
    if deleted:
        core.delete_command(google['id'])
    else:
        core.save_command(google['name'], 'url', google['target'], google['phrases'], False, google['id'])
    assert not core.execute('weather tomorrow', defer_browser=True)['success']
    assert not core.launcher.mock_calls
    assert core.execute('amazon.com')['success']


@pytest.mark.parametrize('phrase,action,target', [
    ('weather tomorrow', 'search', 'weather tomorrow'),
    ('amazon.com', 'url', 'https://amazon.com'),
])
def test_deferred_browser_dispatch(core, phrase, action, target):
    result = core.execute(phrase, defer_browser=True)
    assert result['success'] and result['browser_action'] == action
    assert result['browser_target'] == target
    assert not core.launcher.mock_calls and not core.history()
    finished = core.finish_browser_action(action, True, 'Opened.')
    assert finished['success']
    assert core.history()[0]['trigger_phrase'] == ('[web search]' if action == 'search' else '[website open]')


@pytest.mark.parametrize('action,method', [
    ('search', 'search_web'), ('music', 'play_youtube'), ('url', 'open_registered_url'),
])
def test_worker_dispatch_and_errors(core, qtbot, action, method):
    worker = BrowserWorker(core.launcher, action, 'payload', None)
    received = []
    worker.completed.connect(lambda success, message: received.append((success, message)))
    worker.run()
    assert received == [(True, 'Browser action completed.')]
    getattr(core.launcher, method).assert_called_once_with('payload')
    assert len(core.launcher.mock_calls) == 1
    getattr(core.launcher, method).side_effect = RuntimeError('private payload')
    worker.run()
    assert received[-1] == (False, 'The browser action could not be executed.')


@pytest.mark.parametrize('phrase,method', [
    ('amazon.com', 'open_registered_url'), ('weather tomorrow', 'search_web'),
])
def test_browser_failures_never_persist_payload(core, phrase, method):
    getattr(core.launcher, method).side_effect = RuntimeError('private payload')
    assert not core.execute(phrase)['success']
    assert core.history()[0]['error_message'] == 'Browser action failed.'
    serialized = json.dumps(core.history())
    assert phrase not in serialized and 'private payload' not in serialized


def test_forged_direct_intent_is_revalidated(core, monkeypatch):
    intent = CommandIntent(IntentType.OPEN_WEBSITE, 'https://user:pass@example.com',
                           source=DIRECT_WEBSITE_SOURCE)
    monkeypatch.setattr(core, 'interpret', lambda _: InterpretationResult(True, intent, confidence=1.0))
    assert not core.execute('request', defer_browser=True)['success']
    assert not core.launcher.mock_calls


def test_offline_snapshot_and_packaging_contract():
    assert {'com', 'org', 'in', 'uk', 'xn--fiqs8s'} <= top_level_domains()
    assert len(top_level_domains()) > 1000
    tree = ast.parse((settings.BASE_DIR / 'pet-animal.spec').read_text(encoding='utf-8'))
    analysis = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == 'Analysis')
    datas = next(keyword.value for keyword in analysis.keywords if keyword.arg == 'datas')
    literal_pairs = [ast.literal_eval(item) for item in datas.elts if isinstance(item, ast.Tuple)
                     and all(isinstance(element, ast.Constant) for element in item.elts)]
    assert ('assets/domains', 'assets/domains') in literal_pairs
    assert (settings.BASE_DIR / 'assets/domains/tlds-alpha-by-domain.txt').is_file()


def test_direct_launcher_logs_no_address(monkeypatch, caplog):
    monkeypatch.setattr('webbrowser.open', lambda _: True)
    address = 'https://example.com/private-website-token'
    assert WindowsLauncher().open_registered_url(address)[0]
    assert address not in caplog.text


def test_controller_and_typed_voice_submission_use_worker(core, qtbot, monkeypatch):
    monkeypatch.setattr(settings, 'STATE_FILE', core.root / 'state.json')
    controller = ApplicationController(core)
    controller.manager.hide()
    try:
        for signal, phrase, trigger in (
            (controller.pet.command_box.command_submitted, 'amazon.com', '[website open]'),
            (controller.pet.command_box.voice_command_submitted, 'Weather Tomorrow', '[web search]'),
        ):
            signal.emit(phrase)
            qtbot.waitUntil(lambda: bool(core.history()) and core.history()[0]['trigger_phrase'] == trigger)
            qtbot.waitUntil(lambda: not controller._browser_workers)
        core.launcher.open_registered_url.assert_called_once_with('https://amazon.com')
        core.launcher.search_web.assert_called_once_with('Weather Tomorrow')
    finally:
        QApplication.instance().aboutToQuit.disconnect(controller.shutdown)
        controller.shutdown()
        core._closed_by_controller = True
        controller.pet.hide()
        controller.manager.hide()
