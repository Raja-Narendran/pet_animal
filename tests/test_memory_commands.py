"""Explicit memory commands and memory-informed actions preserve the secure pipeline."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.commands.interpreter import (
    CommandIntent, IntentType, MatchReason, MemoryResolver, RuleBasedIntentInterpreter,
)
from src.commands.interpreter.patterns import APPLICATION_ALIASES


@pytest.mark.parametrize('phrase,key,value,kind', [
    ('remember my name as Naren', 'user.name', 'Naren', 'PROFILE'),
    ('Please save my preferred browser as Google Chrome', 'preferred.browser', 'Google Chrome', 'PREFERENCE'),
    ('remember my editor is VS Code', 'preferred.editor', 'VS Code', 'PREFERENCE'),
    (r'remember that my project folder is K:\My Projects\Pet Animal', 'project.folder', r'K:\My Projects\Pet Animal', 'KNOWLEDGE'),
    (r'remember project.pet_animal.path as K:\pet_animal', 'project.pet_animal.path', r'K:\pet_animal', 'KNOWLEDGE'),
    ('save preferred.code_editor = VS Code', 'preferred.editor', 'VS Code', 'PREFERENCE'),
    ('remember my nickname as Mr. Naren!', 'user.nickname', 'Mr. Naren!', 'PROFILE'),
    ('remember this note: Do not forget the deployment checklist.', 'important.note', 'Do not forget the deployment checklist.', 'NOTE'),
    ('remember my current project as Pet Animal', 'current_project', 'Pet Animal', 'CONTEXT'),
    ('my name is Naren, remember that', 'user.name', 'Naren', 'PROFILE'),
])
def test_explicit_store_has_canonical_key_type_and_original_value(phrase, key, value, kind):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.matched and result.command_id is None
    assert result.intent.intent == IntentType.MEMORY_STORE
    assert (result.intent.target, result.intent.value, result.intent.memory_type) == (key, value, kind)


@pytest.mark.parametrize('phrase,key', [
    ('What is my name?', 'user.name'),
    ('tell me my nickname', 'user.nickname'),
    ('what browser do I prefer', 'preferred.browser'),
    ('which browser do I prefer?', 'preferred.browser'),
    ('what is my editor', 'preferred.editor'),
    ('what is my pet animal project path', 'project.pet_animal.path'),
    ('what do you remember about preferred.browser?', 'preferred.browser'),
    ('recall project.pet_animal.path', 'project.pet_animal.path'),
])
def test_queries_resolve_only_a_structured_target(phrase, key):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.matched and result.intent.intent == IntentType.MEMORY_QUERY
    assert result.intent.target == key
    assert result.intent.value is None


@pytest.mark.parametrize('phrase,key', [
    ('forget my preferred browser', 'preferred.browser'),
    ('delete memory preferred.editor', 'preferred.editor'),
    ('remove memory my name', 'user.name'),
    ('forget memory project.pet_animal.path', 'project.pet_animal.path'),
])
def test_forgetting_produces_an_intent_without_deleting(phrase, key):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.matched and result.intent.intent == IntentType.MEMORY_FORGET
    assert result.intent.target == key and result.command_id is None


@pytest.mark.parametrize('phrase', [
    "Don't remember my name as Naren",
    'do not save my preferred browser as Chrome',
    'never forget my preferred browser',
])
def test_negated_memory_commands_remain_vetoed(phrase):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert not result.matched and result.reason == MatchReason.NEGATED_COMMAND


@pytest.mark.parametrize('phrase', [
    'My name is Naren', 'I use Chrome every day', 'VS Code is my editor',
    'forget everything', 'remember everything I say', 'remember system.secret as password',
])
def test_unstructured_conversation_is_not_stored_or_deleted(phrase):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert not result.matched


@pytest.mark.parametrize('phrase,key', [
    ('open my browser', 'preferred.browser'),
    ('start my preferred browser', 'preferred.browser'),
    ('open my editor', 'preferred.editor'),
    ('launch my code editor', 'preferred.editor'),
])
def test_memory_aware_interpreter_emits_preference_keys(phrase, key):
    result = RuleBasedIntentInterpreter(memory_preferences=True).interpret(phrase)
    assert result.matched and result.intent.intent == IntentType.OPEN_APPLICATION
    assert result.intent.target == key


def commands(target='chrome', enabled=True):
    return [dict(id='registered-command', action_type='application', target=target, enabled=enabled)]


def preference(value='Chrome', **changes):
    values = dict(memory_id='preference-record', key='preferred.browser', value=value,
                  sensitive=False, confidence=1.0)
    values.update(changes)
    return SimpleNamespace(**values)


def resolver(match, exists=True):
    retriever = MagicMock()
    retriever.preference_exists.return_value = exists
    retriever.resolve_preference.return_value = match
    return MemoryResolver(retriever), retriever


def test_preference_resolution_is_read_only_and_requires_a_registered_command():
    instance, retriever = resolver(preference())
    intent = CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.browser')
    result = instance.resolve(intent, commands(), APPLICATION_ALIASES)
    assert result.matched and result.command_id == 'registered-command'
    assert result.intent.target == 'chrome' and result.memory_id == 'preference-record'
    retriever.resolve_preference.assert_called_once_with('preferred.browser', consume=False, min_confidence=.85)
    retriever.consume.assert_not_called()


@pytest.mark.parametrize('kind,match', [
    ('disabled', None), ('expired', None), ('sensitive', preference(sensitive=True)),
    ('low_confidence', preference(confidence=.4)), ('unsafe', preference(r'C:\Tools\unknown.exe')),
    ('shell', preference('cmd /c calc.exe')), ('url', preference('https://example.com')),
])
def test_unavailable_or_unsafe_saved_preference_blocks_the_legacy_default(kind, match):
    instance, retriever = resolver(match)
    result = instance.resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.browser'),
                              commands(), APPLICATION_ALIASES)
    assert not result.matched and result.command_id is None
    retriever.consume.assert_not_called()


def test_absent_preference_preserves_legacy_default_but_not_disabled_command():
    instance, retriever = resolver(None, exists=False)
    intent = CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.browser')
    assert instance.resolve(intent, commands(), APPLICATION_ALIASES).intent.target == 'chrome'
    blocked = instance.resolve(intent, commands(enabled=False), APPLICATION_ALIASES)
    assert not blocked.matched and blocked.reason == MatchReason.DISABLED_COMMAND
    retriever.consume.assert_not_called()


def test_preference_cannot_enable_a_disabled_or_deleted_command():
    instance, retriever = resolver(preference())
    intent = CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.browser')
    assert instance.resolve(intent, commands(enabled=False), APPLICATION_ALIASES).reason == MatchReason.DISABLED_COMMAND
    assert instance.resolve(intent, [], APPLICATION_ALIASES).reason == MatchReason.UNAVAILABLE_COMMAND
    retriever.consume.assert_not_called()


def test_live_registered_application_alias_can_resolve_a_preference():
    instance, retriever = resolver(preference('Personal Editor'))
    aliases = dict(APPLICATION_ALIASES, **{'approved-app-id': {'personal editor'}})
    result = instance.resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.editor'),
                              commands('approved-app-id'), aliases)
    assert result.matched and result.intent.target == 'approved-app-id'
    assert result.memory_id == 'preference-record'
    retriever.consume.assert_not_called()


def test_ambiguous_alias_or_command_cannot_execute():
    instance, retriever = resolver(preference('browser'))
    aliases = {'chrome': {'browser'}, 'notepad': {'browser'}}
    intent = CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.browser')
    assert instance.resolve(intent, commands(), aliases).reason == MatchReason.AMBIGUOUS_TARGET
    duplicates = commands() + [dict(commands()[0], id='another-command')]
    instance, retriever = resolver(preference())
    assert instance.resolve(intent, duplicates, APPLICATION_ALIASES).reason == MatchReason.AMBIGUOUS_COMMAND
    retriever.consume.assert_not_called()


def test_preference_consumption_is_explicit_and_only_after_command_resolution():
    instance, retriever = resolver(preference())
    result = instance.resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.browser'),
                              commands(), APPLICATION_ALIASES, consume=True)
    assert result.matched
    retriever.consume.assert_called_once_with('preference-record')


def test_future_low_confidence_intent_cannot_use_a_preference():
    instance, retriever = resolver(preference())
    result = instance.resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.browser', confidence=.5),
                              commands(), APPLICATION_ALIASES)
    assert not result.matched and result.reason == MatchReason.LOW_CONFIDENCE
    retriever.resolve_preference.assert_not_called()
    retriever.consume.assert_not_called()


@pytest.fixture
def memory_core(tmp_path):
    from src.core.application import ApplicationCore
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened')
    launcher.open_registered_url.return_value = (True, 'Opened')
    core = ApplicationCore(tmp_path, launcher)
    yield core
    core.close()


def save_preference(core, key, value, **metadata):
    category = next(row['id'] for row in core.categories() if row['name'] == 'Important Notes')
    return core.save_memory(category, key, key, value, memory_type='PREFERENCE', **metadata)


def test_explicit_memory_store_query_and_forget_are_confirmed_and_private(memory_core):
    core = memory_core
    proposal = core.execute(r'remember project.pet_animal.path as K:\My Private Project')
    token = proposal['memory_confirmation']
    assert not core.memories() and not core.history()
    assert core.confirm_memory(token)['success']
    result = core.execute('what is my pet animal project path')
    assert result['success'] and result['message'] == r'K:\My Private Project'
    memory = core.memory_service.find_existing('project.pet_animal.path')
    assert memory['access_count'] == 1 and memory['source'] == 'COMMAND'
    deletion = core.execute('forget project.pet_animal.path')
    assert core.get_memory(memory['id']) is not None
    assert core.confirm_memory(deletion['memory_confirmation'])['success']
    assert core.get_memory(memory['id']) is None
    assert not core.history() and not core.launcher.mock_calls


@pytest.mark.parametrize('phrase', [
    'save my preferred browser as Chrome',
    'remember my editor is VS Code',
    'remember this note: Do not share this private project title.',
])
def test_pending_and_cancelled_memory_commands_do_not_persist_or_enter_history(memory_core, phrase):
    proposal = memory_core.execute(phrase)
    token = proposal['memory_confirmation']
    assert not memory_core.memories() and not memory_core.history()
    memory_core.cancel_memory_confirmation(token)
    with pytest.raises(ValueError, match='expired'):
        memory_core.confirm_memory(token)
    assert not memory_core.memories() and not memory_core.history()
    assert not memory_core.launcher.mock_calls


def test_memory_confirmation_cannot_be_replayed(memory_core):
    proposal = memory_core.execute('save my preferred browser as Chrome')
    token = proposal['memory_confirmation']
    assert memory_core.confirm_memory(token)['success']
    with pytest.raises(ValueError, match='expired'):
        memory_core.confirm_memory(token)
    assert len(memory_core.memories()) == 1
    assert not memory_core.history()


def test_memory_confirmation_expires_without_saving(memory_core, monkeypatch):
    monkeypatch.setattr('src.core.application.time.monotonic', lambda: 1000.0)
    proposal = memory_core.execute('save my preferred browser as Chrome')
    monkeypatch.setattr('src.core.application.time.monotonic', lambda: 1300.0)
    with pytest.raises(ValueError, match='expired'):
        memory_core.confirm_memory(proposal['memory_confirmation'])
    assert not memory_core.memories() and not memory_core.history()


def test_conflicting_proposal_cannot_overwrite_an_intervening_edit(memory_core):
    memory_id = save_preference(memory_core, 'preferred.browser', 'Chrome')
    proposal = memory_core.execute('save my preferred browser as Notepad')
    assert memory_core.get_memory(memory_id)['memory_value'] == 'Chrome'
    memory_core.memory_service.update_memory(memory_id, value='Calculator', confirmed=True)
    with pytest.raises(ValueError, match='changed'):
        memory_core.confirm_memory(proposal['memory_confirmation'])
    assert memory_core.get_memory(memory_id)['memory_value'] == 'Calculator'
    assert not memory_core.history()


def test_pending_delete_cannot_remove_an_intervening_edit(memory_core):
    memory_id = save_preference(memory_core, 'preferred.browser', 'Chrome')
    proposal = memory_core.execute('forget my preferred browser')
    memory_core.memory_service.update_memory(memory_id, value='Notepad', confirmed=True)
    with pytest.raises(ValueError, match='changed'):
        memory_core.confirm_memory(proposal['memory_confirmation'])
    assert memory_core.get_memory(memory_id)['memory_value'] == 'Notepad'
    assert not memory_core.history()


@pytest.mark.parametrize('key,value,phrase,expected', [
    ('preferred.browser', 'Notepad', 'open my browser', 'notepad'),
    ('preferred.editor', 'VS Code', 'open my editor', 'vscode'),
])
def test_preferences_reach_the_existing_executor_and_count_only_consumption(memory_core, key, value, phrase, expected):
    memory_id = save_preference(memory_core, key, value)
    before = memory_core.db.total_changes
    interpreted = memory_core.interpret(phrase)
    assert interpreted.matched and interpreted.intent.target == expected
    assert interpreted.command_id and interpreted.memory_id == memory_id
    assert memory_core.db.total_changes == before
    assert memory_core.get_memory(memory_id)['access_count'] == 0
    assert memory_core.execute(phrase)['success']
    memory_core.launcher.open_application.assert_called_once_with(expected)
    assert memory_core.get_memory(memory_id)['access_count'] == 1
    assert memory_core.history()[0]['command_id'] == interpreted.command_id
    assert memory_core.history()[0]['trigger_phrase'] == 'open ' + expected


@pytest.mark.parametrize('condition', ['disabled', 'expired', 'low_confidence', 'unsafe'])
def test_unusable_stored_preference_never_launches_the_default_or_leaks_its_value(memory_core, condition):
    value = 'private-unapproved-target-987.exe' if condition == 'unsafe' else 'Chrome'
    metadata = {'confidence': .2} if condition == 'low_confidence' else {}
    memory_id = save_preference(memory_core, 'preferred.browser', value, **metadata)
    if condition == 'disabled':
        memory_core.memory_service.update_memory(memory_id, enabled=False)
    if condition == 'expired':
        memory_core.memory_service.update_memory(memory_id, lifetime='temporary',
            memory_scope='TEMPORARY', expires_at='2000-01-01T00:00:00+00:00', confirmed=True)
    assert not memory_core.execute('open my browser')['success']
    assert not memory_core.launcher.mock_calls
    assert memory_core.get_memory(memory_id)['access_count'] == 0
    assert memory_core.history()[0]['trigger_phrase'] == '[unsupported command]'
    if condition == 'unsafe':
        import json
        assert value not in json.dumps(memory_core.history())


@pytest.mark.parametrize('app_status', ['disabled', 'repair'])
def test_disabled_or_unsafe_registered_application_does_not_consume_the_preference(memory_core, monkeypatch, app_status):
    memory_id = save_preference(memory_core, 'preferred.editor', 'VS Code')
    blocked = SimpleNamespace(name='Editor', enabled=app_status != 'disabled', needs_repair=app_status == 'repair')
    monkeypatch.setattr(memory_core, 'get_registered_application', lambda target: blocked)
    assert not memory_core.execute('open my editor')['success']
    assert not memory_core.launcher.mock_calls
    assert memory_core.get_memory(memory_id)['access_count'] == 0


def test_preference_is_ignored_outside_its_profile_and_consumed_inside_it(memory_core):
    memory_id = save_preference(memory_core, 'preferred.browser', 'Notepad',
        memory_scope='PROFILE', scope_id='work')
    assert not memory_core.execute('open my browser')['success']
    assert not memory_core.launcher.mock_calls
    assert memory_core.get_memory(memory_id)['access_count'] == 0
    memory_core.memory_service.set_profile('work')
    assert memory_core.execute('open my browser')['success']
    memory_core.launcher.open_application.assert_called_once_with('notepad')
    assert memory_core.get_memory(memory_id)['access_count'] == 1


def test_memory_cannot_bypass_a_corrupted_command_configuration(memory_core):
    import json
    memory_id = save_preference(memory_core, 'preferred.browser', 'Chrome')
    chrome = next(command for command in memory_core.commands() if command['target'] == 'chrome')
    with memory_core.db:
        memory_core.db.execute('UPDATE commands SET action_config=? WHERE id=?',
            (json.dumps({'target': 'cmd /c calc.exe'}), chrome['id']))
    assert not memory_core.execute('open my browser')['success']
    assert not memory_core.launcher.mock_calls
    assert memory_core.get_memory(memory_id)['access_count'] == 0


@pytest.mark.parametrize('phrase', [
    'save my preferred browser as Chrome', 'what browser do I prefer',
    'forget my preferred browser', 'what is my pet animal project path',
])
def test_memory_phrases_remain_reserved_from_custom_commands(memory_core, phrase):
    with pytest.raises(ValueError, match='reserved'):
        memory_core.save_command('Hijacked memory', 'application', 'notepad', [phrase])


def test_confirmation_cannot_cross_an_active_profile_change(memory_core):
    proposal = memory_core.execute('save my preferred browser as Notepad')
    memory_core.memory_service.set_profile('work')
    with pytest.raises(ValueError, match='profile changed'):
        memory_core.confirm_memory(proposal['memory_confirmation'])
    assert not memory_core.memories() and not memory_core.history()


@pytest.mark.parametrize('phrase', [
    'save my preferred browser as Chrome', 'forget my preferred browser',
])
def test_memory_commands_cannot_edit_another_profiles_record(memory_core, phrase):
    memory_id = save_preference(memory_core, 'preferred.browser', 'Notepad',
        memory_scope='PROFILE', scope_id='work')
    result = memory_core.execute(phrase)
    assert not result['success'] and 'another profile' in result['message']
    assert 'memory_confirmation' not in result
    assert memory_core.get_memory(memory_id)['memory_value'] == 'Notepad'
    assert not memory_core.history() and not memory_core.launcher.mock_calls


def test_sensitive_memory_commands_never_decrypt_or_launch_a_preference(memory_core, monkeypatch):
    from src.core import secrets
    category = next(row['id'] for row in memory_core.categories() if row['sensitive'])
    monkeypatch.setattr(secrets, 'encrypt', lambda value: 'dpapi:test-ciphertext')
    decrypt = MagicMock(side_effect=AssertionError('Commands must not decrypt sensitive memory'))
    monkeypatch.setattr(secrets, 'decrypt', decrypt)
    memory_id = memory_core.save_memory(category, 'Private browser', 'preferred.browser',
        'private-sensitive-value-1122', memory_type='PREFERENCE')
    preview_changes = memory_core.db.total_changes
    assert not memory_core.interpret('open my browser').matched
    assert memory_core.db.total_changes == preview_changes
    queried = memory_core.execute('what browser do I prefer')
    assert queried['success'] and 'Memory Manager' in queried['message']
    assert 'private-sensitive-value-1122' not in queried['message']
    for phrase in ('save my preferred browser as Chrome', 'forget my preferred browser'):
        result = memory_core.execute(phrase)
        assert not result['success'] and 'memory_confirmation' not in result
    assert not memory_core.history()
    assert not memory_core.execute('open my browser')['success']
    decrypt.assert_not_called()
    assert not memory_core.launcher.mock_calls
    assert memory_core.get_memory(memory_id)['memory_value'] == '••••••••'
    assert memory_core.get_memory(memory_id)['access_count'] == 1


@pytest.mark.parametrize('phrase,kind', [
    ('recall memory my deployment location', IntentType.MEMORY_QUERY),
    ('what do you remember about my deployment location', IntentType.MEMORY_QUERY),
    ('forget memory my deployment location', IntentType.MEMORY_FORGET),
])
def test_explicit_custom_alias_intents_leave_resolution_to_the_memory_service(phrase, kind):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.matched and result.intent.intent == kind
    assert result.intent.target == 'my deployment location'


@pytest.mark.parametrize('phrase', ['forget memory everything', 'delete memory all', 'remove memory *'])
def test_explicit_forget_never_becomes_a_bulk_deletion(phrase):
    assert not RuleBasedIntentInterpreter().interpret(phrase).matched


def test_custom_alias_query_and_forget_resolve_the_same_canonical_record(memory_core):
    category = next(row['id'] for row in memory_core.categories() if row['name'] == 'Important Notes')
    memory_id = memory_core.save_memory(category, 'Deployment location', 'deployment.location',
        r'K:\Private Deployment', aliases=['my deployment location'])
    before = memory_core.db.total_changes
    assert memory_core.interpret('recall memory my deployment location').intent.target == 'my deployment location'
    assert memory_core.db.total_changes == before
    query = memory_core.execute('recall memory my deployment location')
    assert query['success'] and query['message'] == r'K:\Private Deployment'
    assert memory_core.get_memory(memory_id)['access_count'] == 1
    deletion = memory_core.execute('forget memory my deployment location')
    assert memory_core.get_memory(memory_id) is not None
    assert memory_core.confirm_memory(deletion['memory_confirmation'])['success']
    assert memory_core.get_memory(memory_id) is None
    assert not memory_core.history() and not memory_core.launcher.mock_calls


def test_new_memory_syntax_cannot_execute_a_previously_registered_legacy_phrase(memory_core):
    import uuid
    from src.core.application import now
    phrase = 'remember this note: Do not share private-secret-444'
    chrome = next(command for command in memory_core.commands() if command['target'] == 'chrome')
    # Simulate a phrase saved before this memory syntax was reserved.
    with memory_core.db:
        memory_core.db.execute('INSERT INTO command_phrases VALUES (?,?,?,?,?)',
            (str(uuid.uuid4()), chrome['id'], phrase, phrase.casefold(), now()))
    result = memory_core.execute(phrase)
    assert 'memory_confirmation' in result and not result['success']
    assert not memory_core.memories() and not memory_core.history()
    assert not memory_core.launcher.mock_calls


@pytest.mark.parametrize('phrase', [
    r'remember project.pet_animal.path as K:\Private Projects\Build.V2.',
    'save my preferred browser as Google Chrome',
    'remember this note: Do not share CaseSensitiveName.',
])
def test_voice_compatibility_preserves_original_memory_payload(memory_core, phrase):
    assert memory_core.resolve_voice_phrase(phrase) == phrase


def test_future_interpreter_contract_does_not_require_rule_based_alias_attributes(memory_core):
    from src.commands.interpreter import IntentInterpreter, InterpretationResult
    class FutureInterpreter(IntentInterpreter):
        def interpret(self, phrase):
            return InterpretationResult(True, CommandIntent(IntentType.OPEN_APPLICATION, 'chrome'),
                                        confidence=1.0)
    memory_core.interpreter = FutureInterpreter()
    assert memory_core.execute('a future interpreter request')['success']
    memory_core.launcher.open_application.assert_called_once_with('chrome')


@pytest.mark.parametrize('target', [None, '', 'x' * 201])
def test_invalid_future_memory_query_is_rejected_without_history_or_retrieval(memory_core, target):
    from src.commands.interpreter import InterpretationResult
    future = MagicMock()
    future.interpret.return_value = InterpretationResult(
        True, CommandIntent(IntentType.MEMORY_QUERY, target), confidence=1.0)
    memory_core.interpreter = future
    result = memory_core.execute('future memory request')
    assert not result['success']
    assert not memory_core.history() and not memory_core.launcher.mock_calls


def test_preference_expiring_at_consumption_boundary_cannot_launch(memory_core, monkeypatch):
    memory_id = save_preference(memory_core, 'preferred.browser', 'Chrome')
    assert memory_core.interpret('open my browser').matched
    # Consume rechecks current lifetime; expiration at this boundary returns no match.
    monkeypatch.setattr(memory_core.memory_retriever, 'consume', lambda memory_id: None)
    result = memory_core.execute('open my browser')
    assert not result['success']
    assert not memory_core.launcher.mock_calls
    assert memory_core.get_memory(memory_id)['access_count'] == 0


def test_opt_in_resolver_consumption_rejects_an_expired_record():
    instance, retriever = resolver(preference())
    retriever.consume.return_value = None
    result = instance.resolve(CommandIntent(IntentType.OPEN_APPLICATION, 'preferred.browser'),
                              commands(), APPLICATION_ALIASES, consume=True)
    assert not result.matched and result.reason == MatchReason.UNAVAILABLE_COMMAND
    assert result.memory_id is None


def test_custom_password_memory_query_reveals_decrypted_value(memory_core):
    category_id = next(c['id'] for c in memory_core.categories() if c['name'] == 'Password')
    memory_core.save_memory(
        category_id=category_id,
        title="Office password",
        key="office.password",
        value="SecretOffice123!",
    )
    res = memory_core.execute("what is my Office password?")
    assert res['success'] is True
    assert res['message'] == "SecretOffice123!"

