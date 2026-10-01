"""End-to-end headless and Qt regressions for one shared command pipeline."""
import json
from unittest.mock import MagicMock, call
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox
from src.app.controller import ApplicationController
from src.core.application import ApplicationCore
from src.commands.interpreter import CommandIntent, IntentType, InterpretationResult, MatchReason
from src.services.windows_launcher import WindowsLauncher
from .test_command_interpreter import OPEN_PHRASES
from .test_command_normalizer import NEGATIVE_PHRASES


@pytest.fixture
def core(tmp_path):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened')
    launcher.open_registered_url.return_value = (True, 'Opened')
    launcher.search_web.return_value = (True, 'Search opened')
    launcher.play_youtube.return_value = (True, 'Playback opened')
    instance = ApplicationCore(tmp_path, launcher)
    yield instance
    instance.close()


@pytest.mark.parametrize('phrase,target', OPEN_PHRASES)
def test_smart_application_routes_to_registered_action(core, phrase, target):
    interpretation = core.interpret(phrase)
    assert interpretation.matched and interpretation.command_id
    assert core.execute(phrase)['success']
    core.launcher.open_application.assert_called_once_with(target)
    assert core.history()[0]['command_id'] == interpretation.command_id
    assert core.history()[0]['trigger_phrase'] in ('open ' + target, phrase.casefold())


@pytest.mark.parametrize('phrase', NEGATIVE_PHRASES)
def test_negation_never_calls_launcher_even_with_exact_registration(core, phrase):
    core.save_command('Negative exact phrase', 'application', 'chrome', [phrase])
    assert core.interpret(phrase).reason == MatchReason.NEGATED_COMMAND
    assert not core.execute(phrase)['success']
    assert not core.execute(core.resolve_voice_phrase(phrase))['success']
    assert not core.launcher.mock_calls
    assert all(row['trigger_phrase'] == '[unsupported command]' for row in core.history())


def test_exact_and_voice_normalized_custom_priority(core):
    core.save_command('Custom exact', 'application', 'notepad', ['Can you open Chrome?'])
    result = core.interpret('Can you open Chrome?')
    assert result.reason == MatchReason.EXACT_PHRASE and result.confidence == 1.0
    assert core.execute('Can you open Chrome?')['success']
    core.launcher.open_application.assert_called_once_with('notepad')
    core.launcher.reset_mock()
    core.save_command('Custom Tamil', 'application', 'notepad', ['Chrome open பண்ணு'])
    assert core.execute('Chrome open பண்ணு')['success']
    core.launcher.open_application.assert_called_once_with('notepad')
    core.launcher.reset_mock()
    core.save_command('Canonical custom', 'application', 'calculator', ['open google chrome'])
    assert core.execute('please google chrome open pannu')['success']
    core.launcher.open_application.assert_called_once_with('calculator')


@pytest.mark.parametrize('phrase', ['can you open chrome', 'open google chrome', 'Chrome ah open pannu', 'start my browser'])
def test_disabled_and_deleted_command_never_bypassed(core, phrase):
    chrome = next(c for c in core.commands() if c['target'] == 'chrome')
    core.save_command(chrome['name'], 'application', 'chrome', chrome['phrases'], False, chrome['id'])
    assert core.interpret(phrase).reason == MatchReason.DISABLED_COMMAND
    assert not core.execute(phrase)['success']
    core.delete_command(chrome['id'])
    assert core.interpret(phrase).reason == MatchReason.UNAVAILABLE_COMMAND
    assert not core.execute(phrase)['success']
    assert not core.launcher.mock_calls


def test_disabled_exact_and_canonical_custom_block_smart_fallback(core):
    core.save_command('Disabled custom', 'application', 'notepad', ['Can you open Chrome?'], False)
    assert not core.execute('Can you open Chrome?')['success']
    core.save_command('Disabled canonical', 'application', 'notepad', ['open google chrome'], False)
    assert not core.execute('google chrome open pannu')['success']
    assert not core.launcher.mock_calls


def test_ambiguous_commands_and_low_confidence_need_clarification(core):
    core.save_command('Second Chrome', 'application', 'chrome', ['browse now'])
    assert core.interpret('could you bring up chrome').reason == MatchReason.AMBIGUOUS_COMMAND
    assert not core.execute('could you bring up chrome')['success']
    assert core.execute('open chrome')['success']  # Exact unique phrase still wins.
    core.launcher.reset_mock()
    low = core.execute('open code')
    assert not low['success'] and 'Did you mean' in low['message']
    assert not core.launcher.mock_calls


@pytest.mark.parametrize('phrase,handler,target', [
    ('Could you search Google for Salesforce DevOps?', 'search_web', 'salesforce devops'),
    ('find Salesforce CI/CD', 'search_web', 'salesforce ci/cd'),
    ('சென்னை weather search பண்ணு', 'search_web', 'சென்னை weather'),
    ('can you play Shape of You', 'play_youtube', 'shape of you'),
    ('Shape of You song play pannu', 'play_youtube', 'shape of you'),
])
def test_browser_uses_existing_service_and_private_history(core, phrase, handler, target):
    assert core.execute(phrase)['success']
    getattr(core.launcher, handler).assert_called_once_with(target)
    assert target not in json.dumps(core.history(), ensure_ascii=False)
    assert core.history()[0]['trigger_phrase'] in ('[web search]', '[music playback]')


@pytest.mark.parametrize('phrase,target', [('can you search for cats', 'google'), ('can you play a song', 'youtube')])
def test_smart_browser_cannot_bypass_disabled_registration(core, phrase, target):
    record = next(c for c in core.commands() if c['target'] == f'https://www.{target}.com')
    core.save_command(record['name'], 'url', record['target'], record['phrases'], False, record['id'])
    assert not core.execute(phrase, defer_browser=True)['success']
    assert not core.launcher.mock_calls


@pytest.mark.parametrize('phrase', ['open photoshop', 'cmd /c calc.exe', 'powershell open chrome',
                                   'rm -rf /', 'del chrome', 'delete chrome', 'open chrome & calc',
                                   'open https://user:pass@example.com', 'open chrome\nopen notepad'])
def test_shell_and_unsupported_inputs_never_reach_services(core, phrase):
    assert not core.execute(phrase)['success']
    assert not core.launcher.mock_calls
    assert phrase not in json.dumps(core.history())


def test_execution_revalidates_interpreted_command_and_does_not_trust_intent(core):
    chrome = next(c for c in core.commands() if c['target'] == 'chrome')
    with core.db:
        core.db.execute('UPDATE commands SET action_config=? WHERE id=?', (json.dumps({'target': 'cmd /c calc'}), chrome['id']))
    assert not core.execute('open chrome')['success']
    assert not core.launcher.mock_calls


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:pass@example.com', 'https://example.com:444', 'https://example.com\nfoo'])
def test_registered_url_validation_is_still_enforced(core, url):
    youtube = next(c for c in core.commands() if c['target'] == 'https://www.youtube.com')
    with core.db:
        core.db.execute('UPDATE commands SET action_config=? WHERE id=?', (json.dumps({'target': url}), youtube['id']))
    assert not core.execute('open youtube')['success']
    core.launcher.open_registered_url.assert_not_called()


def test_low_confidence_from_future_interpreter_cannot_execute(core):
    core.interpreter = MagicMock()
    intent = CommandIntent(IntentType.OPEN_APPLICATION, 'chrome', confidence=.5, source='future')
    core.interpreter.interpret.return_value = InterpretationResult(True, intent, confidence=.5)
    assert not core.execute('a request from a future interpreter')['success']
    assert not core.launcher.mock_calls


@pytest.mark.parametrize('phrase', ['save my name as Naren', 'my name is Naren, remember that'])
def test_memory_alias_proposes_only_and_retains_existing_privacy(core, phrase):
    proposal = core.execute(phrase)
    assert proposal['confirmation'] == 'Naren'
    assert not core.memories() and not core.history()
    core.confirm_name(proposal['confirmation'])
    assert core.execute('tell me my name')['message'] == 'Naren'
    assert core.execute('do you remember my name')['message'] == 'Naren'
    assert not core.history()
    with pytest.raises(ValueError):
        core.save_command('Reserved memory', 'application', 'notepad', [phrase])


def test_interpretation_is_read_only(core):
    before = core.db.total_changes
    result = core.interpret('save my name as Secret Name')
    assert result.intent.value == 'Secret Name'
    assert core.interpret('can you open chrome').command_id
    assert core.db.total_changes == before
    assert not core.memories() and not core.history() and not core.launcher.mock_calls


def test_real_launcher_logs_no_search_payload(monkeypatch, caplog):
    monkeypatch.setattr('webbrowser.open', lambda url: True)
    query = 'private-smart-search-12345'
    assert WindowsLauncher().search_web(query)[0]
    assert query not in caplog.text


def test_manager_tester_and_typed_voice_signals_share_pipeline(qtbot, tmp_path, monkeypatch):
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened Chrome')
    core = ApplicationCore(tmp_path, launcher)
    controller = ApplicationController(core)
    try:
        controller.manager.navigation.setCurrentRow(2)
        controller.manager.smart_input.setText('Can you open Chrome please?')
        controller.manager.smart_test_button.click()
        assert 'OPEN_APPLICATION' in controller.manager.smart_result.text()
        assert 'Execution: Not executed' in controller.manager.smart_result.text()
        assert not core.history() and not launcher.mock_calls
        for signal in (controller.pet.command_box.command_submitted, controller.pet.command_box.voice_command_submitted):
            signal.emit('Could you bring up Chrome?')
        assert launcher.open_application.call_args_list == [call('chrome'), call('chrome')]
        launcher.reset_mock()
        controller.pet.command_box.voice_command_submitted.emit('chrome open panna vendam')
        assert not launcher.mock_calls
        assert controller.pet.command_box.input_field.text() == 'chrome open panna vendam'
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
        assert not controller.execute('save my name as Naren')['success']
        assert not core.memories()
    finally:
        controller.shutdown()
        controller.pet.hide()
        controller.manager.hide()
        QApplication.instance().aboutToQuit.disconnect(controller.shutdown)
