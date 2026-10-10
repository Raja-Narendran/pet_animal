"""Service and lifecycle regressions; no installed applications are required."""
import json
import sqlite3
import sys
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox
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
    assert core.db.execute('PRAGMA user_version').fetchone()[0] == 7
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
    assert core.stats()['commands'] == 8


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
        for index in range(7):
            app.manager.navigation.setCurrentRow(index)
            qapp.processEvents()
            assert app.manager.content_layout.count() >= 1
            if app.manager.page == "Workflows":
                assert app.manager.content_layout.itemAt(0).widget() is app.manager.workflows_panel
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


def test_voice_mode_settings_toggle_and_validation(core, qapp, monkeypatch):
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', core.root / 'state.json')
    app = ApplicationController(core)
    try:
        # New settings default to Google; the legacy multilingual flag stays false.
        assert core.app_settings()['voice_mode'] == 'google'
        assert settings.VOICE_MODE == 'google'
        assert settings.GOOGLE_VOICE_LANGUAGE == 'en-IN'
        assert settings.VOICE_MULTILINGUAL is False

        # Switch to multilingual -> Whisper
        cfg = core.app_settings()
        cfg['voice_mode'] = 'multilingual'
        core.save_settings(cfg)
        assert settings.VOICE_MULTILINGUAL is True

        # Switch back to google
        cfg['voice_mode'] = 'google'
        core.save_settings(cfg)
        assert settings.VOICE_MULTILINGUAL is False

        # Switch to english raises ValueError since Vosk is removed
        with pytest.raises(ValueError, match='Invalid voice mode'):
            core.save_settings(dict(cfg, voice_mode='english'))

        # Invalid voice_mode raises ValueError
        with pytest.raises(ValueError, match='Invalid voice mode'):
            core.save_settings(dict(cfg, voice_mode='invalid_mode'))

        # Legacy config without voice_mode is accepted and defaults to Google.
        legacy = dict(cfg)
        del legacy['voice_mode']
        core.validate_settings(legacy)
    finally:
        core.listeners.clear()
        app.pet.tray_icon.hide()
        app.pet.hide()
        app.manager.hide()
        qapp.aboutToQuit.disconnect(app.shutdown)




def test_voice_hotkey_settings_legacy_export_backup(core):
    assert core.app_settings()['voice_hotkey_enabled'] is False
    core.save_settings(dict(core.app_settings(), voice_hotkey_enabled=True))
    assert core.export_configuration()['settings']['voice_hotkey_enabled'] is True
    backup = core.backup()
    legacy = core.app_settings()
    del legacy['voice_hotkey_enabled']
    core.save_settings(legacy)
    assert core.app_settings()['voice_hotkey_enabled'] is False
    core.restore(backup)
    assert core.app_settings()['voice_hotkey_enabled'] is True
    # An older database does not contain this key; restore uses the default.
    with sqlite3.connect(backup) as db:
        db.execute("DELETE FROM app_settings WHERE key='voice_hotkey_enabled'")
    core.restore(backup)
    assert core.app_settings()['voice_hotkey_enabled'] is False
    payload = core.export_configuration()
    payload['commands'] = []
    payload['routines'] = []
    del payload['settings']['voice_hotkey_enabled']
    core.import_configuration(payload)
    assert core.app_settings()['voice_hotkey_enabled'] is False


@pytest.mark.parametrize('value', [1, 0, 'true', None])
def test_voice_hotkey_setting_requires_bool(core, value):
    with pytest.raises(ValueError, match='voice_hotkey_enabled'):
        core.save_settings(dict(core.app_settings(), voice_hotkey_enabled=value))


def test_google_voice_settings_compatibility(core):
    config = core.app_settings()
    assert config['voice_mode'] == 'google'
    assert config['google_voice_language'] == 'en-IN'
    for mode in ('google', 'multilingual'):
        core.save_settings(dict(config, voice_mode=mode, google_voice_language='ta-IN'))
        assert core.app_settings()['voice_mode'] == mode
        assert core.app_settings()['google_voice_language'] == 'ta-IN'
    with pytest.raises(ValueError, match='Google voice language'):
        core.save_settings(dict(config, google_voice_language='invalid'))
    core.db.execute("INSERT OR REPLACE INTO app_settings VALUES ('voice_mode', '\"english\"')")
    core.db.execute("DELETE FROM app_settings WHERE key='google_voice_language'")
    core.db.commit()
    assert core.app_settings()['voice_mode'] == 'google'
    assert core.app_settings()['google_voice_language'] == 'en-IN'
    payload = core.export_configuration()
    payload['settings']['voice_mode'] = 'english'
    del payload['settings']['google_voice_language']
    payload['commands'] = []  # Import is append-only; avoid duplicating seeded phrases.
    core.import_configuration(payload)
    assert core.app_settings()['voice_mode'] == 'google'
    assert core.app_settings()['google_voice_language'] == 'en-IN'
    core.save_settings(dict(config, voice_mode='multilingual', google_voice_language='ta-IN'))
    backup = core.backup()
    with sqlite3.connect(backup) as db:
        db.execute("INSERT OR REPLACE INTO app_settings VALUES ('voice_mode', '\"english\"')")
        db.execute("DELETE FROM app_settings WHERE key='google_voice_language'")
    core.restore(backup)
    assert core.app_settings()['voice_mode'] == 'google'
    assert core.app_settings()['google_voice_language'] == 'en-IN'


def test_google_settings_selector_and_saved_language(core, qapp, monkeypatch):
    from PyQt6.QtWidgets import QComboBox, QLabel, QPushButton
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', core.root / 'state.json')
    controller = ApplicationController(core)
    try:
        from src.app.manager_window import PAGES
        controller.manager.navigation.setCurrentRow(PAGES.index('Settings'))
        combos = controller.manager.findChildren(QComboBox)
        engine = next(c for c in combos if c.findData('google') >= 0)
        language = next(c for c in combos if c.findData('ta-IN') >= 0)
        notice = next(w for w in controller.manager.findChildren(QLabel)
                      if w.text() == 'Sends recorded audio to Google; requires internet')
        assert engine.currentData() == 'google'
        assert not language.isHidden() and not notice.isHidden()
        engine.setCurrentIndex(engine.findData('multilingual'))
        assert language.isHidden() and notice.isHidden()
        engine.setCurrentIndex(engine.findData('google'))
        language.setCurrentIndex(language.findData('ta-IN'))
        save = next(b for b in controller.manager.findChildren(QPushButton) if b.text() == 'Save preferences')
        save.click()
        assert core.app_settings()['voice_mode'] == 'google'
        assert core.app_settings()['google_voice_language'] == 'ta-IN'
        assert settings.GOOGLE_VOICE_LANGUAGE == 'ta-IN'
    finally:
        qapp.aboutToQuit.disconnect(controller.shutdown)
        core.listeners.clear()
        controller.manager.software_state.shutdown()
        controller.pet.pet.anim_timer.stop()
        controller.pet.tray_icon.hide()
        controller.pet.hide()
        controller.manager.hide()
