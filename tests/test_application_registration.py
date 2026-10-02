"""Approval, persistence, command routing, trust revalidation and restore regressions."""
from dataclasses import replace
import json
import sqlite3
from unittest.mock import MagicMock
import pytest
from src.core.application import ApplicationCore
from src.services.windows_launcher import WindowsLauncher
from src.services.software_discovery import DiscoveredApplication, DiscoverySource, ApplicationValidator, ValidationStatus
from src.commands.interpreter import IntentType


@pytest.fixture
def core(tmp_path):
    instance = ApplicationCore(tmp_path / 'data', WindowsLauncher())
    yield instance
    instance.close()


@pytest.fixture
def candidate(tmp_path):
    path = tmp_path / 'Spotify.exe'
    path.write_bytes(b'MZ')
    return DiscoveredApplication.candidate('Spotify', str(path), DiscoverySource.START_MENU_USER)


def approve(core, candidate, **kwargs):
    return core.register_application(candidate, phrases=['open spotify', 'launch spotify', 'start spotify'], **kwargs)


def test_detection_never_authorizes_and_approval_persists(core, candidate, monkeypatch):
    popen = MagicMock()
    monkeypatch.setattr('subprocess.Popen', popen)
    assert ApplicationValidator().validate(candidate).launchable
    assert not core.execute('open spotify')['success'] and not popen.called
    app_id = approve(core, candidate)
    assert core.get_registered_application(app_id).enabled
    root = core.root
    other = ApplicationCore(root)
    try:
        assert other.get_registered_application(app_id).name == 'Spotify'
        assert other.execute('open spotify')['success']
        popen.assert_called_once_with([candidate.executable_path], shell=False)
    finally:
        other.close()


@pytest.mark.parametrize('phrase', ['open spotify', 'launch spotify', 'can you start spotify', 'start spotify please', 'spotify open pannu'])
def test_dynamic_smart_phrases_use_application_id(core, candidate, monkeypatch, phrase):
    app_id = approve(core, candidate)
    launch = MagicMock(return_value=(True, 'Opened'))
    monkeypatch.setattr(core.launcher, 'open_application', launch)
    result = core.interpret(phrase)
    assert result.matched and result.intent.intent == IntentType.OPEN_APPLICATION and result.intent.target == app_id
    assert core.execute(phrase)['success']
    launch.assert_called_once_with(app_id)


def test_alias_edit_custom_phrases_and_rename(core, candidate, monkeypatch):
    app_id = approve(core, candidate, aliases=['spotify', 'music app'])
    monkeypatch.setattr('subprocess.Popen', MagicMock())
    assert core.execute('can you open music app')['success']
    core.save_command('Music', 'application', app_id, ['music time', 'open streaming player'], command_id=next(c['id'] for c in core.commands() if c['target'] == app_id))
    assert core.execute('music time')['success'] and core.execute('can you launch streaming player')['success']
    core.update_application(app_id, 'My Music', ['new music'])
    assert core.execute('open my music')['success'] and core.execute('open new music')['success']
    assert not core.interpret('can you launch music app').matched


def test_conflicts_rollback_approval_and_alias_edits(core, candidate):
    with pytest.raises(ValueError, match='Phrase already registered'):
        core.register_application(candidate, phrases=['open notepad'])
    assert not core.list_registered_applications()
    app_id = approve(core, candidate)
    with pytest.raises(ValueError):
        core.update_application(app_id, 'Changed', ['chrome'])
    assert core.get_registered_application(app_id).name == 'Spotify'
    with pytest.raises(ValueError, match='already registered'):
        approve(core, candidate)


def test_optional_command_and_alias_conflicts(core, candidate, tmp_path):
    app_id = core.register_application(candidate, aliases=['spotify'])
    assert not core.interpret('open spotify').matched
    other = tmp_path / 'Other.exe'
    other.touch()
    with pytest.raises(ValueError, match='alias already registered'):
        core.register_application(replace(candidate, name='Other', executable_path=str(other)), aliases=['spotify'])
    assert len(core.list_registered_applications()) == 1
    core.save_command('Open music', 'application', app_id, ['music now'])
    assert core.interpret('can you start spotify').matched


@pytest.mark.parametrize('name', ['cmd.exe', 'powershell.exe', 'pwsh.exe', 'regedit.exe', 'wscript.exe', 'cscript.exe', 'mshta.exe', 'rundll32.exe', 'unins000.exe', 'setup.exe', 'helper.exe', 'Spotify.ps1', 'Spotify.vbs', 'Spotify.js', 'Spotify.cmd', 'Spotify.bat'])
def test_forged_launchable_flag_cannot_register_unsafe_target(core, candidate, tmp_path, name):
    path = tmp_path / name
    path.touch()
    forged = replace(candidate, executable_path=str(path), launchable=True, validation_status=ValidationStatus.VALID)
    with pytest.raises(ValueError):
        approve(core, forged)
    assert not core.list_registered_applications()


def test_disabled_removed_and_missing_apps_never_launch(core, candidate, monkeypatch):
    popen = MagicMock()
    monkeypatch.setattr('subprocess.Popen', popen)
    app_id = approve(core, candidate)
    core.set_application_enabled(app_id, False)
    assert core.execute('open spotify')['message'] == 'Spotify is currently disabled.'
    assert not core.execute('can you start spotify')['success'] and not popen.called
    core.set_application_enabled(app_id, True)
    assert core.execute('open spotify')['success']
    popen.reset_mock()
    from pathlib import Path
    Path(candidate.executable_path).unlink()
    assert 'Rediscover' in core.execute('launch spotify')['message'] and not popen.called
    with pytest.raises(ValueError):
        core.set_application_enabled(app_id, True)
    core.unregister_application(app_id)
    assert not core.execute('open spotify')['success']
    assert all(not command['enabled'] for command in core.commands() if command['target'] == app_id)
    assert not popen.called
    core.restore(core.backup())  # Removed registrations leave disabled commands.


def test_launcher_only_accepts_ids_and_revalidates_live_registration(core, candidate, monkeypatch, tmp_path):
    popen = MagicMock()
    monkeypatch.setattr('subprocess.Popen', popen)
    app_id = approve(core, candidate)
    assert not core.launcher.open_application(candidate.executable_path)[0]
    assert not WindowsLauncher().open_application(app_id)[0]
    bad = tmp_path / 'powershell.exe'
    bad.touch()
    with core.db:
        core.db.execute('UPDATE registered_applications SET executable_path=? WHERE id=?', (str(bad), app_id))
    assert not core.launcher.open_application(app_id)[0]
    assert not core.execute('open spotify')['success'] and not popen.called


def test_sqlite_restore_marks_missing_paths_needs_repair(core, candidate):
    app_id = approve(core, candidate)
    backup = core.backup()
    from pathlib import Path
    Path(candidate.executable_path).unlink()
    core.restore(backup)
    app = core.get_registered_application(app_id)
    assert not app.enabled and app.needs_repair
    assert not core.execute('open spotify')['success']


def test_restore_rejects_dangerous_registration_preserving_live_data(core, candidate, tmp_path):
    app_id = approve(core, candidate)
    backup = core.backup()
    bad = tmp_path / 'cmd.exe'
    bad.touch()
    with sqlite3.connect(backup) as db:
        db.execute('UPDATE registered_applications SET executable_path=? WHERE id=?', (str(bad), app_id))
    with pytest.raises(ValueError):
        core.restore(backup)
    assert core.get_registered_application(app_id).executable_path == candidate.executable_path


def test_configuration_round_trip_remaps_ids_and_missing_paths(core, candidate, tmp_path):
    app_id = approve(core, candidate)
    payload = core.export_configuration()
    payload['commands'] = [c for c in payload['commands'] if c['target'] == app_id]
    from pathlib import Path
    Path(candidate.executable_path).unlink()
    other = ApplicationCore(tmp_path / 'other')
    try:
        other.import_configuration(payload)
        imported = other.list_registered_applications()[0]
        assert imported.id != app_id and not imported.enabled and imported.needs_repair
        assert any(c['target'] == imported.id for c in other.commands())
        assert not other.execute('open spotify')['success']
    finally:
        other.close()


def test_migration_from_version_one_preserves_existing_records(tmp_path):
    from src.config.settings import settings
    root = tmp_path / 'legacy'
    (root / 'database').mkdir(parents=True)
    with sqlite3.connect(root / 'database/petanimal.db') as db:
        db.executescript((settings.BASE_DIR / 'src/database/migrations/001_initial.sql').read_text(encoding='utf-8-sig'))
        db.execute('INSERT INTO applications VALUES (?,?,?)', ('legacy', 'Legacy unused metadata', 'never launched'))
    core = ApplicationCore(root)
    try:
        assert core.db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert core.rows('SELECT * FROM applications')[0]['name'] == 'Legacy unused metadata'
        assert not core.list_registered_applications()
    finally:
        core.close()


def test_legacy_backup_is_migrated_in_memory_without_changing_source(core):
    from src.config.settings import settings
    core.confirm_name('Legacy user')
    backup = core.backup()
    # Build an actual shipped V1 schema, rather than relabeling a newer schema.
    legacy = backup.with_suffix('.legacy.db')
    with sqlite3.connect(legacy) as db, sqlite3.connect(backup) as original:
        db.executescript((settings.BASE_DIR / 'src/database/migrations/001_initial.sql').read_text(encoding='utf-8-sig'))
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            columns = ','.join(row[1] for row in db.execute(f'PRAGMA table_info({table})'))
            records = original.execute(f'SELECT {columns} FROM {table}').fetchall()
            if records:
                placeholders = ','.join('?' for _ in records[0])
                db.executemany(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', records)
    db.close()
    original.close()
    legacy.replace(backup)
    before = backup.read_bytes()
    core.confirm_name('Changed')
    core.restore(backup)
    assert core.get_memory_by_key('user.name')['memory_value'] == 'Legacy user'
    assert core.db.execute('PRAGMA user_version').fetchone()[0] == 3
    assert backup.read_bytes() == before


def test_resolved_path_must_match_original_approval(core, candidate, monkeypatch, tmp_path):
    from pathlib import Path
    approve(core, candidate)
    other = tmp_path / 'Another.exe'
    other.touch()
    monkeypatch.setattr(Path, 'resolve', lambda self, *args, **kwargs: other)
    popen = MagicMock()
    monkeypatch.setattr('subprocess.Popen', popen)
    assert not core.execute('open spotify')['success']
    assert not core.launcher.open_application(core.list_registered_applications()[0].id)[0]
    assert not popen.called


def test_bulk_refresh_adds_all_valid_apps_and_commands_without_launching(core, candidate, tmp_path, monkeypatch):
    other = tmp_path / 'Editor.exe'
    other.touch()
    dangerous = tmp_path / 'powershell.exe'
    dangerous.touch()
    popen = MagicMock()
    monkeypatch.setattr('subprocess.Popen', popen)
    results = [candidate, replace(candidate, name='Editor', executable_path=str(other)),
               replace(candidate, executable_path=str(dangerous), launchable=True)]
    notifications = MagicMock()
    core.listeners.append(notifications)
    summary = core.register_discovered_applications(results)
    assert summary == dict(added=2, already_added=0, commands_created=2, invalid=1, failed=0)
    assert core.interpret('open spotify').matched and core.interpret('can you launch editor').matched
    notifications.assert_called_once()
    assert not popen.called
    repeated = core.register_discovered_applications(results)
    assert repeated['added'] == 0 and repeated['already_added'] == 2
    assert len(core.list_registered_applications()) == 2 and not popen.called


def test_bulk_refresh_resolves_phrase_and_builtin_alias_collisions(core, candidate, tmp_path):
    core.save_command('My shortcut', 'application', 'notepad', ['open spotify'])
    chrome = tmp_path / 'Chrome.exe'
    chrome.touch()
    duplicate = tmp_path / 'OtherSpotify.exe'
    duplicate.touch()
    summary = core.register_discovered_applications([candidate,
        replace(candidate, name='Google Chrome', executable_path=str(chrome)),
        replace(candidate, executable_path=str(duplicate))])
    assert summary['added'] == 3 and summary['failed'] == 0
    assert core.interpret('open spotify').intent.target == 'notepad'
    assert core.interpret('can you open chrome').intent.target == 'chrome'
    assert core.interpret('can you open google chrome').intent.target == 'chrome'
    registered = core.list_registered_applications()
    for app in registered:
        assert core.interpret('can you launch ' + app.aliases[0]).intent.target == app.id
    assert len({app.aliases[0] for app in registered}) == 3


def test_bulk_refresh_preserves_disabled_apps_and_custom_commands(core, candidate):
    app_id = approve(core, candidate)
    command = next(command for command in core.commands() if command['target'] == app_id)
    core.save_command('My music', 'application', app_id, ['music now'], False, command['id'])
    core.set_application_enabled(app_id, False)
    summary = core.register_discovered_applications([candidate])
    assert summary['already_added'] == 1 and summary['commands_created'] == 0
    assert not core.get_registered_application(app_id).enabled
    preserved = core.rows('SELECT name,enabled FROM commands WHERE id=?', (command['id'],))[0]
    assert preserved == dict(name='My music', enabled=0)
    assert not core.execute('music now')['success']


def test_bulk_refresh_adds_command_to_previously_registered_app(core, candidate):
    app_id = core.register_application(candidate)
    assert not core.interpret('can you open spotify').matched
    summary = core.register_discovered_applications([candidate])
    assert summary['added'] == 0 and summary['commands_created'] == 1
    assert core.interpret('can you open spotify').intent.target == app_id
