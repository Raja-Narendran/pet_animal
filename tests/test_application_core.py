"""Service and lifecycle regressions; no installed applications are required."""
import json
import sqlite3
import sys
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox
from src.core.application import ApplicationCore, DEFAULT_PET, normalize
from src.app.controller import ApplicationController


class Launcher:
    def __init__(self):
        self.apps = []
        self.urls = []

    def open_application(self, key):
        self.apps.append(key)
        return True, 'Opened ' + key

    def open_registered_url(self, url):
        self.urls.append(url)
        return True, 'Opened website'


@pytest.fixture
def core(tmp_path):
    service = ApplicationCore(tmp_path, Launcher())
    yield service
    service.close()


def personal(core):
    return next(c['id'] for c in core.categories() if c['name'] == 'Personal Information')


def test_migration_restart_and_memory_crud(tmp_path):
    core = ApplicationCore(tmp_path, Launcher())
    cat = personal(core)
    key = core.save_memory(cat, 'Name', 'user.name', 'Naren')
    assert core.get_memory_by_key('user.name')['memory_value'] == 'Naren'
    core.save_memory(cat, 'My name', 'user.name', 'Nova', 'friend', False, key)
    assert core.get_memory_by_key('user.name') is None
    assert len(core.memories('friend', cat)) == 1
    core.close()
    core = ApplicationCore(tmp_path, Launcher())
    assert core.get_memory(key)['memory_value'] == 'Nova'
    assert core.db.execute('PRAGMA user_version').fetchone()[0] == 1
    assert core.db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    core.delete_memory(key)
    assert core.memories() == []
    assert len(core.profiles()) == 1
    core.close()


@pytest.mark.parametrize('field,value', [('title',''),('key',''),('value',''),('description',None)])
def test_memory_validation(core, field, value):
    fields = dict(category_id=personal(core), title='Name', key='name', value='Naren', description='')
    fields[field] = value
    with pytest.raises(ValueError):
        core.save_memory(**fields)
    assert core.memories() == []


def test_memory_uniqueness_foreign_keys_and_parameterization(core):
    core.save_memory(personal(core), "Name'); DROP TABLE memories;--", 'user.name', 'Naren')
    assert len(core.memories()) == 1
    with pytest.raises(sqlite3.IntegrityError):
        core.save_memory(personal(core), 'Other', 'user.name', 'Other')
    with pytest.raises(ValueError):
        core.save_memory('missing', 'Other', 'other', 'Other')


def test_confirmed_memory_patterns_do_not_record_values(core):
    proposal = core.execute('REMEMBER my name as Naren')
    assert proposal['confirmation'] == 'Naren'
    assert not core.memories() and not core.history()
    core.confirm_name(proposal['confirmation'])
    assert core.execute('WHAT IS MY NAME')['message'] == 'Naren'
    core.confirm_name('Nova')
    assert len(core.memories()) == 1
    assert not core.history()


def test_memory_import_atomic_and_round_trip(core, tmp_path):
    core.save_memory(personal(core), 'Name', 'user.name', 'Naren')
    export = core.export_memories()
    other = ApplicationCore(tmp_path / 'other', Launcher())
    other.import_memories(export)
    assert other.get_memory_by_key('user.name')['memory_value'] == 'Naren'
    other.close()
    export['memories'].insert(0, dict(title='Test', memory_key='new.key', memory_value='test', category='New category', enabled=1, description=''))
    with pytest.raises(ValueError):
        core.import_memories(export)
    assert not core.get_memory_by_key('new.key')
    assert all(c['name'] != 'New category' for c in core.categories())


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows DPAPI')
def test_sensitive_values_encrypted_masked_and_not_exported(core):
    cat = next(c['id'] for c in core.categories() if c['sensitive'])
    key = core.save_memory(cat, 'Card', 'card.number', '1234-5678-secret')
    stored = core.db.execute('SELECT memory_value FROM memories WHERE id=?', (key,)).fetchone()[0]
    assert stored.startswith('dpapi:') and 'secret' not in stored
    assert core.get_memory(key)['memory_value'] == '••••••••'
    assert core.get_memory(key, reveal=True)['memory_value'] == '1234-5678-secret'
    assert core.memories('secret') == []
    assert core.export_memories()['memories'] == []


def test_phrase_normalization_conflict_and_disabled_commands(core):
    assert normalize('  OPEN   Notepad ') == 'open notepad'
    assert core.execute('  OPEN   Notepad ')['success']
    with pytest.raises(ValueError):
        core.save_command('Duplicate', 'application', 'chrome', ['OPEN NOTEPAD'])
    record = next(c for c in core.commands() if c['target'] == 'notepad')
    core.save_command(record['name'], 'application', 'notepad', ['write notes'], False, record['id'])
    assert not core.execute('open notepad')['success']
    assert not core.execute('write notes')['success']
    assert core.launcher.apps == ['notepad']


@pytest.mark.parametrize('phrase', ['help','what is my name','remember my name as Alice'])
def test_reserved_patterns_cannot_be_registered(core, phrase):
    with pytest.raises(ValueError):
        core.save_command('Reserved', 'application', 'notepad', [phrase])


@pytest.mark.parametrize('action,target', [('shell','calc'),('application','powershell'),('application','cmd /c calc'),('url','file:///C:/secret'),('url','javascript:alert(1)'),('url','http://example.com'),('url','https://user:password@example.com'),('url','https://example.com:bad'),('url','https://example.com\nmalicious')])
def test_reject_unsafe_actions(core, action, target):
    with pytest.raises(ValueError):
        core.save_command('Unsafe', action, target, ['do unsafe'])
    assert not core.launcher.apps and not core.launcher.urls


def test_unsupported_text_is_redacted(core):
    assert not core.execute('powershell secret-password')['success']
    assert core.history()[0]['trigger_phrase'] == '[unsupported command]'
    assert 'secret-password' not in json.dumps(core.history())


def test_custom_https_command_and_missing_application(core):
    core.save_command('Docs', 'url', 'https://docs.python.org/3/', ['open docs', 'python docs'])
    assert core.execute('Python DOCS')['success']
    assert core.launcher.urls == ['https://docs.python.org/3/']
    core.launcher.open_application = lambda key: (False, 'Application is not installed')
    assert not core.execute('open chrome')['success']
    assert core.history()[0]['execution_status'] == 'failed'


def test_backup_restore_and_recovery(core):
    core.confirm_name('Naren')
    backup = core.backup()
    core.confirm_name('Changed')
    core.restore(backup)
    assert core.get_memory_by_key('user.name')['memory_value'] == 'Naren'
    assert len(list((core.root / 'backups').glob('*.db'))) == 2
    with pytest.raises(ValueError):
        core.backup(backup)


def test_restore_rejects_triggers_and_preserves_live_data(core):
    core.confirm_name('Naren')
    backup = core.backup()
    connection = sqlite3.connect(backup)
    connection.execute('CREATE TRIGGER injected AFTER INSERT ON memories BEGIN DELETE FROM commands; END')
    connection.close()
    with pytest.raises(ValueError):
        core.restore(backup)
    assert core.get_memory_by_key('user.name')['memory_value'] == 'Naren'


def test_config_import_failure_rolls_back(core):
    payload = core.export_configuration()
    original = core.active_profile()['id']
    with pytest.raises(ValueError):
        core.import_configuration(payload)  # Exact phrase conflicts do not overwrite.
    assert len(core.profiles()) == 1
    assert core.active_profile()['id'] == original
    payload['commands'] = []
    payload['profiles'][0]['config']['size'] = 9999
    with pytest.raises(ValueError):
        core.import_configuration(payload)
    assert core.active_profile()['id'] == original


def test_profile_switch_and_validation(core):
    core.save_profile('Nova', 'builtin-idle', dict(DEFAULT_PET, size=128))
    assert core.active_profile()['name'] == 'Nova'
    assert sum(p['is_active'] for p in core.profiles()) == 1
    with pytest.raises(ValueError):
        core.save_profile('Invalid', 'builtin-idle', dict(DEFAULT_PET, background='url(secret)'))
    assert core.active_profile()['name'] == 'Nova'


def test_asset_import_and_path_restriction(core, tmp_path):
    from PIL import Image
    source = tmp_path / 'pet.png'
    Image.new('RGBA', (128,64), (255,0,0,255)).save(source)
    asset_id = core.import_asset(source)
    assert core.asset_path(asset_id).parent == (core.root / 'pets/imported').resolve()
    Image.new('RGBA', (100,64)).save(source)
    with pytest.raises(ValueError):
        core.import_asset(source)
    with core.db:
        core.db.execute('UPDATE pet_assets SET filename=? WHERE id=?', ('../../database/petanimal.db', asset_id))
    with pytest.raises(ValueError):
        core.asset_path(asset_id)


def test_history_stats_and_clear(core):
    core.execute('open notepad')
    core.execute('bad')
    assert core.stats()['today'] == 2
    assert len(core.history('success')) == 1
    core.clear_history()
    assert core.stats()['today'] == 0
    assert core.stats()['commands'] == 7


def test_two_windows_share_configuration_and_close_independently(core, qapp, monkeypatch):
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', core.root / 'state.json')
    app = ApplicationController(core)
    try:
        profile = core.active_profile()
        core.save_profile('Nova', 'builtin-idle', dict(DEFAULT_PET, size=128, always_on_top=False), profile['id'])
        assert app.pet.pet.width() == 128
        assert app.pet.windowTitle() == 'Nova'
        assert not app.pet.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        app.manager.close()
        qapp.processEvents()
        assert not app.manager.isVisible()
        assert app.pet.isVisible()
        app.show_manager()
        for index in range(6):
            app.manager.navigation.setCurrentRow(index)
            qapp.processEvents()
            assert app.manager.content_layout.count() > 1
    finally:
        core.listeners.clear()
        app.pet.tray_icon.hide()
        app.pet.hide()
        app.manager.hide()
        qapp.aboutToQuit.disconnect(app.shutdown)


def test_memory_write_requires_ui_confirmation(core, qapp, monkeypatch):
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', core.root / 'state.json')
    app = ApplicationController(core)
    try:
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
        assert not app.execute('remember my name as Naren')['success']
        assert not core.memories()
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
        assert app.execute('remember my name as Naren')['success']
        assert core.get_memory_by_key('user.name')['memory_value'] == 'Naren'
    finally:
        core.listeners.clear()
        app.pet.tray_icon.hide()
        app.pet.hide()
        app.manager.hide()
        qapp.aboutToQuit.disconnect(app.shutdown)


def test_controller_pet_minimize_and_restore(core, qapp, monkeypatch):
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', core.root / 'state.json')
    app = ApplicationController(core)
    try:
        app.pet.show()
        qapp.processEvents()
        assert app.pet.isVisible()
        assert not app.pet.pet_minimized
        assert not app.pet.command_box.expand_button.isVisible()

        # Click minimize button
        app.pet.min_btn.click()
        qapp.processEvents()
        assert app.pet.pet_minimized
        assert not app.pet.pet.isVisible()
        assert app.pet.command_box.isVisible()
        assert app.pet.command_box.expand_button.isVisible()

        # Click expand button
        app.pet.command_box.expand_button.click()
        qapp.processEvents()
        assert not app.pet.pet_minimized
        assert app.pet.pet.isVisible()
        assert not app.pet.command_box.expand_button.isVisible()

        # Show pet from controller restores it if minimized
        app.pet.min_btn.click()
        qapp.processEvents()
        assert app.pet.pet_minimized
        app.show_pet()
        qapp.processEvents()
        assert not app.pet.pet_minimized
        assert app.pet.pet.isVisible()
    finally:
        core.listeners.clear()
        app.pet.tray_icon.hide()
        app.pet.hide()
        app.manager.hide()
        qapp.aboutToQuit.disconnect(app.shutdown)

