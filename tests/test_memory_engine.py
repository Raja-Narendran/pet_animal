"""Personal Memory Engine behavior through its headless public API."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.core.memory import (MemoryConflict, MemoryConflictType,
                             MemoryQuery, MemoryScope, MemoryService, MemoryType)
from src.core.memory import service as module


@pytest.fixture
def engine():
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA foreign_keys=ON')
    for migration in sorted(Path('src/database/migrations').glob('*.sql')):
        db.executescript(migration.read_text(encoding='utf-8-sig'))
    db.executemany('INSERT INTO memory_categories VALUES (?,?,?)',
                   [('personal', 'Personal Information', 0), ('private', 'Private', 1), ('custom', 'Custom', 0)])
    db.execute("INSERT INTO pet_assets VALUES ('asset','Idle','idle.png',0)")
    stamp = datetime(2026, 10, 2, tzinfo=timezone.utc)
    db.execute('INSERT INTO pet_profiles VALUES (?,?,?,?,?,?)', ('pet-one', 'Husky', 'asset', 1, stamp.isoformat(), stamp.isoformat()))
    db.execute('INSERT INTO pet_profiles VALUES (?,?,?,?,?,?)', ('pet-two', 'Fox', 'asset', 0, stamp.isoformat(), stamp.isoformat()))
    db.commit()
    time = [stamp]
    service = MemoryService(db, session_id='session-one', clock=lambda: time[0])
    service.test_time = time
    yield service
    db.close()


def save(engine, key='project.path', value='K:/pet_animal', **kwargs):
    return engine.create_memory('personal', 'Project path', key, value, **kwargs)


@pytest.mark.parametrize('kind', list(MemoryType))
def test_explicit_types_and_default_importance(engine, kind):
    memory_id = save(engine, key='kind.' + kind.value.lower(), memory_type=kind)
    record = engine.get_memory(memory_id)
    assert record['memory_type'] == kind.value
    assert 0 <= record['importance'] <= 1
    assert record['confidence'] == 1
    assert record['source'] == 'USER_MANUAL'
    assert record['access_count'] == 0
    if kind == MemoryType.CONTEXT:
        assert record['lifetime'] == 'session'
        assert record['session_id'] == engine.session_id
    if kind == MemoryType.SYSTEM:
        assert engine.list_memories() == []
        assert engine.list_memories(include_system=True)[0]['id'] == memory_id


@pytest.mark.parametrize('scope', list(MemoryScope))
def test_scopes_lifetime_and_owner(engine, scope):
    memory_id = save(engine, memory_scope=scope)
    row = engine.get_memory(memory_id)
    assert row['memory_scope'] == scope.value
    if scope == MemoryScope.PROFILE:
        assert row['scope_id'] == 'default'
    elif scope == MemoryScope.PET_PROFILE:
        assert row['scope_id'] == 'pet-one'
    elif scope == MemoryScope.SESSION:
        assert row['lifetime'] == 'session' and row['session_id'] == 'session-one'
    elif scope == MemoryScope.TEMPORARY:
        assert row['lifetime'] == 'temporary' and row['expires_at']
    assert engine.retriever.get_by_key('project.path', consume=False)


@pytest.mark.parametrize('field', ['importance', 'confidence'])
@pytest.mark.parametrize('bad', [-0.1, 1.1, float('inf'), float('nan'), True, '0.5'])
def test_scores_are_finite_bounded_numbers(engine, field, bad):
    with pytest.raises(ValueError):
        save(engine, **{field:bad})
    assert not engine.list_memories()


def test_unknown_confidence_cannot_resolve_action(engine):
    memory_id = save(engine, key='preferred.editor', value='vscode', confidence=None)
    assert engine.get_memory(memory_id)['confidence'] == 0
    assert engine.retriever.resolve_preference('preferred.editor') is None
    assert engine.retriever.preference_exists('preferred.editor')


@pytest.mark.parametrize('metadata', [dict(memory_type='ALIEN'), dict(memory_scope='CLOUD'), dict(lifetime='forever'),
                                      dict(source='AI_SERVER'), dict(expires_at='2026-10-02T12:00:00'),
                                      dict(memory_scope='PET_PROFILE', scope_id='unknown'),
                                      dict(memory_type='CONTEXT', lifetime='persistent'),
                                      dict(memory_scope='GLOBAL', scope_id='wrong'),
                                      dict(tags=['x']*31), dict(aliases='text'), dict(enabled='1')])
def test_invalid_metadata_is_rejected_before_write(engine, metadata):
    with pytest.raises(ValueError):
        save(engine, **metadata)
    assert not engine.list_memories()


def test_listing_filters_metadata_search_and_no_access_tracking(engine):
    first = save(engine, key='user.nickname', value='Nova', tags=['Identity', ' identity '], aliases=['Call Me'])
    second = save(engine, key='preferred.editor', value='vscode', enabled=False)
    assert engine.get_memory(first)['tags'] == ['identity']
    assert [r['id'] for r in engine.list_memories(query='call me')] == [first]
    assert [r['id'] for r in engine.list_memories(query='IDENTITY')] == [first]
    assert [r['id'] for r in engine.list_memories(memory_type='PROFILE')] == [first]
    assert [r['id'] for r in engine.list_memories(enabled=False)] == [second]
    assert engine.get_memory(first)['access_count'] == 0
    assert engine.get_memory(second)['access_count'] == 0


def test_only_consumed_retrieval_records_access(engine):
    memory_id = save(engine)
    assert engine.retriever.get_by_key('project.path', consume=False).memory_id == memory_id
    engine.get_memory(memory_id)
    engine.list_memories()
    assert engine.get_memory(memory_id)['last_accessed_at'] is None
    match = engine.retriever.get_by_key('project.path')
    assert match.memory['access_count'] == 1
    assert match.memory['last_accessed_at'] == engine.now()
    engine.retriever.search('project', consume=False)
    assert engine.get_memory(memory_id)['access_count'] == 1
    engine.retriever.search('project')
    assert engine.get_memory(memory_id)['access_count'] == 2


def test_disabled_and_expired_records_cannot_be_consumed(engine):
    disabled = save(engine, key='disabled', enabled=False)
    expiring = save(engine, key='temporary', lifetime='temporary', expires_at=(engine.test_time[0] + timedelta(minutes=1)).isoformat())
    assert engine.retriever.get_by_key('disabled') is None
    engine.test_time[0] += timedelta(minutes=2)
    assert engine.retriever.get_by_key('temporary') is None
    assert engine.retriever.consume(expiring) is None
    assert not engine.record_access(disabled)
    assert not engine.record_access(expiring)
    assert engine.get_memory(expiring)['access_count'] == 0
    assert engine.list_memories(expired=True)[0]['id'] == expiring
    assert engine.expire_memories() == 1
    assert engine.expire_memories(delete=True) == 1
    assert engine.get_memory(expiring) is None


def test_session_removal_at_shutdown_and_after_crash(engine):
    persistent = save(engine, key='stable')
    first = engine.set_context('current_project', 'Pet Animal')
    assert engine.get_memory(first)['source'] == 'SYSTEM'
    assert engine.close_session() == 1
    assert engine.get_memory(first) is None
    second = engine.set_context('current_application', 'vscode')
    successor = MemoryService(engine.db, session_id='session-two', clock=lambda: engine.test_time[0])
    assert successor.get_memory(second) is None
    assert successor.get_memory(persistent)


def test_startup_removes_expired_records_without_per_record_timers(engine):
    expired = save(engine, key='expired', lifetime='temporary', expires_at=(engine.test_time[0] - timedelta(seconds=1)).isoformat())
    successor = MemoryService(engine.db, session_id='next', clock=lambda: engine.test_time[0])
    assert successor.get_memory(expired) is None


def test_aliases_merge_concepts_and_user_alias_edits_survive_restart(engine):
    first = save(engine, key='user.name', value='Naren')
    second = save(engine, key='my name', value='Naren')
    assert first == second
    assert engine.retriever.get_by_key('MY NAME', consume=False).match_reason == 'ALIAS'
    assert engine.retriever.get_by_key('user.name', consume=False).match_reason == 'EXACT_KEY'
    engine.update_memory(first, aliases=['call me'])
    successor = MemoryService(engine.db, session_id='next', clock=lambda: engine.test_time[0])
    assert successor.get_memory(first)['aliases'] == ['call me']
    assert successor.retriever.get_by_key('my name', consume=False) is None


def test_structured_preference_alias_normalizes_even_before_first_write(engine):
    memory_id = save(engine, key='preferred.code_editor', value='vscode')
    assert engine.get_memory(memory_id)['memory_key'] == 'preferred.editor'
    assert engine.get_memory(memory_id)['memory_type'] == 'PREFERENCE'
    assert engine.retriever.get_by_key('preferred.code_editor', consume=False).memory_id == memory_id


@pytest.mark.parametrize('changes,kind', [(dict(value='Changed'), 'VALUE_CHANGE'),
                                         (dict(memory_type='NOTE'), 'TYPE_CONFLICT'),
                                         (dict(memory_scope='PROFILE'), 'SCOPE_CONFLICT')])
def test_conflicting_updates_require_confirmation(engine, changes, kind):
    memory_id = save(engine)
    with pytest.raises(MemoryConflict) as error:
        engine.update_memory(memory_id, **changes)
    assert error.value.conflict_type == kind
    assert engine.get_memory(memory_id)['memory_value'] == 'K:/pet_animal'
    engine.update_memory(memory_id, confirmed=True, **changes)
    assert engine.get_memory(memory_id)


def test_new_conflicting_alias_value_never_silently_replaces(engine):
    memory_id = save(engine, key='user.name', value='Naren')
    with pytest.raises(MemoryConflict):
        save(engine, key='my name', value='Raja')
    assert engine.get_memory(memory_id)['memory_value'] == 'Naren'
    assert save(engine, key='my name', value='Raja', confirmed=True) == memory_id
    assert engine.get_memory(memory_id)['memory_value'] == 'Raja'


def test_alias_and_key_collision_is_rejected(engine):
    first = save(engine, key='one', aliases=['first'])
    with pytest.raises(ValueError):
        save(engine, key='two', aliases=['FIRST'])
    with pytest.raises(MemoryConflict):
        save(engine, key='first', value='Other')
    save(engine, key='two')
    with pytest.raises(MemoryConflict) as error:
        engine.update_memory(first, key='two')
    assert error.value.conflict_type == MemoryConflictType.DUPLICATE


def test_profile_and_pet_owners_are_enforced_during_retrieval(engine):
    profile = save(engine, key='preferred.browser', value='notepad', memory_scope='PROFILE', scope_id='work')
    pet = save(engine, key='husky.greeting', memory_scope='PET_PROFILE')
    assert engine.retriever.preference_exists('preferred.browser')
    assert engine.retriever.resolve_preference('preferred.browser') is None
    engine.set_profile('work')
    assert engine.retriever.resolve_preference('preferred.browser').memory_id == profile
    with engine.db:
        engine.db.execute("UPDATE pet_profiles SET is_active=0 WHERE id='pet-one'")
        engine.db.execute("UPDATE pet_profiles SET is_active=1 WHERE id='pet-two'")
    assert engine.retriever.get_by_key('husky.greeting') is None
    assert engine.get_memory(pet)['access_count'] == 0


def test_exact_match_wins_over_importance_and_text_search(engine):
    exact = save(engine, key='pet', value='exact', importance=0, confidence=0)
    save(engine, key='project.pet', value='pet', importance=1, confidence=1)
    matches = engine.retriever.retrieve_relevant('pet', consume=False)
    assert matches[0].memory_id == exact
    assert matches[0].match_reason == 'EXACT_KEY'
    assert matches[0].score > matches[1].score
    assert engine.retriever.get_by_key('pe', consume=False) is None


def test_ranking_tags_type_recency_frequency_and_confidence(engine):
    high = save(engine, key='high', tags=['development'], importance=1, confidence=1)
    low = save(engine, key='low', tags=['development'], importance=0, confidence=0)
    matches = engine.retriever.retrieve_by_tags(['DEVELOPMENT'], consume=False)
    assert [m.memory_id for m in matches] == [high, low]
    assert all(m.match_reason == 'TAG' for m in matches)
    assert len(engine.retriever.retrieve_by_type('KNOWLEDGE', consume=False)) == 2
    assert len(engine.get_by_scope('GLOBAL', consume=False)) == 2
    before = engine.retriever.get_by_key('high', consume=False).score
    engine.retriever.get_by_key('high')
    assert engine.retriever.get_by_key('high', consume=False).score > before
    engine.test_time[0] += timedelta(days=10)
    assert engine.retriever.get_by_key('high', consume=False).score < before
    with pytest.raises(ValueError):
        engine.retriever.retrieve_relevant(MemoryQuery(limit=1000))


def test_relationships_are_unique_retrievable_and_cascade(engine):
    source = save(engine, key='project')
    target = save(engine, key='editor', value='vscode')
    edge = engine.create_relationship(source, 'works with', target)
    assert engine.create_relationship(source, 'works_with', target) == edge
    assert engine.get_relationships(source)[0]['target_title'] == 'Project path'
    matches = engine.retriever.retrieve_relationships(source, consume=False)
    assert matches[0].memory_id == target and matches[0].match_reason == 'RELATIONSHIP'
    engine.update_memory(target, enabled=False)
    assert engine.retriever.retrieve_relationships(source) == []
    with pytest.raises(ValueError):
        engine.create_relationship(source, 'uses', source)
    engine.delete_memory(source)
    assert engine.get_relationships() == []


def test_health_counts_are_factual_and_do_not_delete_unused(engine):
    old = save(engine, key='old')
    engine.test_time[0] += timedelta(days=31)
    save(engine, key='disabled', enabled=False)
    save(engine, key='expired', lifetime='temporary', expires_at=(engine.test_time[0]-timedelta(seconds=1)).isoformat())
    health = engine.memory_health()
    assert health == dict(total=3, active=1, disabled=1, expired=1, sensitive=0, unused=1)
    assert engine.get_memory(old)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows DPAPI')
def test_sensitive_encryption_masking_search_export_and_metadata_edits(engine, monkeypatch):
    memory_id = engine.create_memory('private', 'Private note', 'account.private', 'secret-value', tags=['account'])
    ciphertext = engine.db.execute('SELECT memory_value FROM memories WHERE id=?', (memory_id,)).fetchone()[0]
    assert ciphertext.startswith('dpapi:') and 'secret-value' not in ciphertext
    assert engine.get_memory(memory_id)['memory_value'] == module.MASK
    assert engine.get_memory(memory_id, reveal=True)['memory_value'] == 'secret-value'
    monkeypatch.setattr(module.secrets, 'decrypt', lambda value: pytest.fail('Unexpected decryption'))
    assert engine.retriever.get_by_key('account.private').value == module.MASK
    assert engine.retriever.search('secret-value') == []
    assert engine.list_memories(query='secret-value') == []
    assert engine.list_memories(query='account')[0]['memory_value'] == module.MASK
    engine.update_memory(memory_id, title='Updated private note', tags=['private'])
    assert engine.db.execute('SELECT memory_value FROM memories WHERE id=?', (memory_id,)).fetchone()[0] == ciphertext
    engine.update_memory(memory_id, enabled=False)
    assert engine.get_memory(memory_id)['memory_value'] == module.MASK
    assert engine.export_memories()['memories'] == []
    with pytest.raises(MemoryConflict) as error:
        engine.update_memory(memory_id, value='other')
    assert 'secret-value' not in str(error.value) + json.dumps(error.value.existing)


def export_record(**changes):
    record = dict(title='Imported', memory_key='imported.key', memory_value='value', category='Custom', enabled=1, description='')
    record.update(changes)
    return record


def test_safe_export_roundtrips_graph_tags_aliases_and_usage(engine):
    first = save(engine, key='project', tags=['development'], aliases=['my project'])
    second = save(engine, key='preferred.editor', value='vscode')
    engine.retriever.get_by_key('project')
    engine.create_relationship(first, 'uses', second)
    engine.set_context('current_project', 'Private session value')
    payload = engine.export_memories()
    assert payload['version'] == 2
    assert len(payload['memories']) == 2 and len(payload['relationships']) == 1
    assert 'Private session value' not in json.dumps(payload)
    engine.delete_memory(first)
    engine.delete_memory(second)
    summary = engine.import_memories(payload)
    assert summary['new'] == 2
    assert engine.get_by_key('project', consume=False)['tags'] == ['development']
    assert engine.get_by_key('my project', consume=False)['access_count'] == 1
    assert engine.get_by_key('project', consume=False)['source'] == 'IMPORT'
    assert len(engine.get_relationships()) == 1


def test_import_summary_conflicts_duplicates_and_explicit_replacement(engine):
    existing = save(engine, key='imported.key', value='old')
    duplicate = export_record(memory_key='other.key', memory_value='other')
    payload = dict(version=2, memories=[export_record(), duplicate, duplicate])
    summary = engine.preview_import(payload)
    assert (summary['new'], summary['duplicates'], summary['conflicts'], summary['invalid']) == (1, 1, 1, 0)
    with pytest.raises(ValueError):
        engine.import_memories(payload)
    assert engine.get_memory(existing)['memory_value'] == 'old'
    assert not engine.find_existing('other.key')
    engine.import_memories(payload, confirm_conflicts=True)
    assert engine.get_memory(existing)['memory_value'] == 'value'
    assert engine.find_existing('other.key')


@pytest.mark.parametrize('changes', [dict(memory_scope='ALIEN'), dict(confidence=float('nan')),
                                     dict(importance=True), dict(enabled='yes'), dict(tags='bad'),
                                     dict(expires_at='tomorrow'), dict(access_count=-1),
                                     dict(category='Private'), dict(unknown_field='injection'),
                                     dict(memory_value='value\x00secret'), dict(lifetime='session', memory_scope='SESSION')])
def test_invalid_import_is_atomic_and_cannot_inject_metadata(engine, changes):
    payload = dict(version=2, memories=[export_record(memory_key='valid.key'), export_record(**changes)])
    summary = engine.preview_import(payload)
    assert summary['invalid'] >= 1
    with pytest.raises(ValueError):
        engine.import_memories(payload, confirm_conflicts=True)
    assert not engine.find_existing('valid.key')


def test_import_internal_alias_collision_and_relationship_errors_are_atomic(engine):
    payload = dict(version=2, memories=[export_record(memory_key='one', aliases=['shared']), export_record(memory_key='two', aliases=['SHARED'])])
    assert engine.preview_import(payload)['invalid'] == 1
    with pytest.raises(ValueError):
        engine.import_memories(payload)
    payload = dict(version=2, memories=[export_record()], relationships=[dict(source_key='imported.key', relationship_type='uses', target_key='unknown')])
    assert engine.preview_import(payload)['invalid'] == 1
    with pytest.raises(ValueError):
        engine.import_memories(payload)


def test_legacy_export_import_and_strict_duplicate_policy(engine):
    payload = dict(version=1, memories=[export_record()])
    assert engine.import_memories(payload)['new'] == 1
    assert engine.import_memories(payload)['duplicates'] == 1
    with pytest.raises(ValueError):
        engine.import_memories(payload, strict=True)


@pytest.mark.parametrize('changes', [dict(scope_id='other'), dict(lifetime='temporary')])
def test_import_duplicate_keys_with_different_lifecycle_are_invalid(engine, changes):
    first = export_record(memory_key='scoped', memory_scope='PROFILE', scope_id='work')
    second = dict(first, **changes)
    payload = dict(version=2, memories=[first, second])
    assert engine.preview_import(payload)['invalid'] == 1
    with pytest.raises(ValueError):
        engine.import_memories(payload, confirm_conflicts=True)
    assert not engine.find_existing('scoped')


def test_list_memories_state_parameter(engine):
    active_id = save(engine, key='active.item', enabled=True)
    disabled_id = save(engine, key='disabled.item', enabled=False)
    assert active_id in [r['id'] for r in engine.list_memories(state='enabled')]
    assert disabled_id not in [r['id'] for r in engine.list_memories(state='enabled')]
    assert disabled_id in [r['id'] for r in engine.list_memories(state='disabled')]
    assert active_id not in [r['id'] for r in engine.list_memories(state='disabled')]
    with pytest.raises(ValueError, match="not supported"):
        engine.list_memories(state='sensitive')
    with pytest.raises(ValueError, match="not supported"):
        engine.list_memories(state='expired')
    with pytest.raises(ValueError, match="Unknown memory state"):
        engine.list_memories(state='invalid')
