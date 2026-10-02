"""Migration and backup boundaries use temporary databases, never user state."""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config.settings import settings
from src.core.application import ApplicationCore
from src.core import secrets


def legacy_database(root):
    path = root / 'database' / 'petanimal.db'
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        for filename in ('001_initial.sql', '002_registered_applications.sql'):
            db.executescript((settings.BASE_DIR / 'src/database/migrations' / filename).read_text(encoding='utf-8-sig'))
        db.execute('INSERT INTO memory_categories VALUES (?,?,?)', ('personal', 'Personal Information', 0))
        db.execute('INSERT INTO memory_categories VALUES (?,?,?)', ('sensitive', 'Private', 1))
        stamp = '2026-01-01T00:00:00+00:00'
        db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)',
                   ('old-name', 'personal', 'Name', 'user.name', 'Naren', 'saved before upgrade', 1, stamp, stamp))
        ciphertext = secrets.encrypt('private-migration-value')
        db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)',
                   ('old-private', 'sensitive', 'Private', 'private.key', ciphertext, '', 1, stamp, stamp))
    return path, ciphertext


def test_v2_migration_preserves_ids_timestamps_and_exact_ciphertext(tmp_path):
    path, ciphertext = legacy_database(tmp_path)
    core = ApplicationCore(tmp_path, MagicMock())
    try:
        assert core.db.execute('PRAGMA user_version').fetchone()[0] == 3
        name = core.get_memory('old-name')
        assert (name['memory_key'], name['memory_value'], name['memory_type']) == ('user.name', 'Naren', 'PROFILE')
        assert name['source'] == 'MIGRATION'
        assert name['created_at'] == '2026-01-01T00:00:00+00:00'
        assert core.db.execute('SELECT memory_value FROM memories WHERE id=?', ('old-private',)).fetchone()[0] == ciphertext
        assert core.get_memory('old-private')['memory_value'] == '••••••••'
        assert core.get_memory('old-private', reveal=True)['memory_value'] == 'private-migration-value'
    finally:
        core.close()


def test_failed_memory_migration_rolls_back_without_destroying_records(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    path, ciphertext = legacy_database(root)
    broken_root = tmp_path / 'broken-runtime'
    migrations = broken_root / 'src/database/migrations'
    migrations.mkdir(parents=True)
    (migrations / '003_personal_memory_engine.sql').write_text(
        'ALTER TABLE memories ADD COLUMN failed_upgrade TEXT; THIS IS INVALID SQL;', encoding='utf-8')
    monkeypatch.setattr(settings, 'BASE_DIR', broken_root)
    with pytest.raises(sqlite3.Error):
        ApplicationCore(root, MagicMock())
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert 'failed_upgrade' not in [row[1] for row in db.execute('PRAGMA table_info(memories)')]
        assert db.execute('SELECT memory_value FROM memories WHERE id=?', ('old-private',)).fetchone()[0] == ciphertext
        assert db.execute('SELECT count(*) FROM memories').fetchone()[0] == 2


@pytest.fixture
def core(tmp_path):
    app = ApplicationCore(tmp_path, MagicMock())
    yield app
    app.close()


def category(core):
    return next(item['id'] for item in core.categories() if not item['sensitive'])


def test_backup_restores_metadata_graph_and_encrypted_values(core):
    service = core.memory_service
    left = service.create_memory(category(core), 'Editor', 'preferred.editor', 'vscode', memory_type='PREFERENCE',
                                 tags=['development'], aliases=['coding preference'], importance=.9, confidence=.95)
    right = service.create_memory(category(core), 'Project', 'project.pet_animal.path', 'K:\\pet_animal')
    relation = service.create_relationship(left, 'used_for', right)
    private_category = next(item['id'] for item in core.categories() if item['sensitive'])
    secret_id = service.create_memory(private_category, 'Private note', 'private.note', 'private-backup-value', memory_type='NOTE')
    service.record_access(left)
    backup = core.backup()
    service.delete_memory(left)
    service.delete_memory(secret_id)
    core.restore(backup)
    restored = core.get_memory(left)
    assert restored['tags'] == ['development'] and 'coding preference' in restored['aliases']
    assert (restored['importance'], restored['confidence'], restored['access_count']) == (.9, .95, 1)
    assert service.get_relationships(left)[0]['id'] == relation
    assert core.get_memory(secret_id, reveal=True)['memory_value'] == 'private-backup-value'
    assert core.get_memory(secret_id)['memory_value'] == '••••••••'


@pytest.mark.parametrize('column,value', [
    ('last_accessed_at', 'not-a-date'),
    ('session_id', 'unexpected-session'),
])
def test_restore_rejects_invalid_new_memory_metadata_and_preserves_live_database(core, column, value):
    core.confirm_name('Before backup')
    backup = core.backup()
    with sqlite3.connect(backup) as db:
        db.execute(f'UPDATE memories SET {column}=? WHERE memory_key=?', (value, 'user.name'))
    core.confirm_name('Live name')
    with pytest.raises(ValueError):
        core.restore(backup)
    assert core.get_memory_by_key('user.name', consume=False)['memory_value'] == 'Live name'


def test_restore_never_revives_saved_runtime_session(core):
    service = core.memory_service
    context_id = service.create_memory(category(core), 'Current task', 'current_task', 'Temporary task',
                                       memory_type='CONTEXT', memory_scope='SESSION')
    backup = core.backup()
    service.delete_memory(context_id)
    core.restore(backup)
    assert core.get_memory(context_id) is None


def test_backup_rejects_modified_alias_normalization(core):
    core.confirm_name('Naren')
    backup = core.backup()
    with sqlite3.connect(backup) as db:
        db.execute("UPDATE memory_aliases SET normalized_alias='forged-normalization' WHERE alias='my name'")
    with pytest.raises(ValueError):
        core.restore(backup)
    assert core.get_memory_by_key('user.name', consume=False)['memory_value'] == 'Naren'
