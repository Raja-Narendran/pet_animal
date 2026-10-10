"""Spotify requests are tested without network access or launching apps."""
import json
from unittest.mock import MagicMock, patch
from urllib.parse import quote
import pytest
from src.services.windows_launcher import WindowsLauncher
from src.core.application import ApplicationCore
from src.commands.parser import RuleBasedCommandParser
from src.app.controller import BrowserWorker

@pytest.mark.parametrize('available,error', [(True, False), (False, False), (True, True)])
def test_auto_activation_and_fallback(available, error):
    launcher = WindowsLauncher()
    song = 'தமிழ் & Shape / You?#'
    encoded = quote(song, safe='')
    with patch.object(launcher, 'spotify_available', return_value=available), patch('os.startfile', create=True) as start, patch('webbrowser.open', return_value=True) as browser:
        if error:
            start.side_effect = OSError('unavailable')
        success, message = launcher.play_music(song, 'spotify', 'auto')
        assert success and 'Opening' in message and 'Playing' not in message
        if available:
            start.assert_called_once_with('spotify:search:' + encoded, 'open')
        else:
            start.assert_not_called()
        if available and not error:
            browser.assert_not_called()
        else:
            browser.assert_called_once_with('https://open.spotify.com/search/' + encoded)

@pytest.mark.parametrize('outcome', [False, OSError('browser unavailable')])
def test_browser_failure_does_not_change_provider(outcome):
    launcher = WindowsLauncher()
    with patch.object(launcher, 'spotify_available') as available, patch.object(launcher, 'play_youtube') as youtube, patch('webbrowser.open') as browser:
        if isinstance(outcome, Exception):
            browser.side_effect = outcome
        else:
            browser.return_value = outcome
        assert not launcher.play_music('shape of you', 'spotify', 'browser')[0]
        available.assert_not_called()
        youtube.assert_not_called()

@pytest.mark.parametrize('song,provider,mode', [('', 'spotify', 'auto'), ('a\nb', 'spotify', 'auto'), ('a\tb', 'spotify', 'auto'), ('a', 'evil', 'auto'), ('a', 'spotify', 'evil')])
def test_invalid_request_never_launches(song, provider, mode):
    with patch('webbrowser.open') as browser, patch('os.startfile', create=True) as start:
        assert not WindowsLauncher().play_music(song, provider, mode)[0]
        browser.assert_not_called()
        start.assert_not_called()

def test_youtube_delegation():
    launcher = WindowsLauncher()
    with patch.object(launcher, 'play_youtube', return_value=(True, 'Opened')) as play:
        assert launcher.play_music('song', 'youtube') == (True, 'Opened')
        play.assert_called_once_with('song')

@pytest.fixture
def core(tmp_path):
    launcher = MagicMock()
    launcher.play_music.return_value = (True, 'Opened')
    service = ApplicationCore(tmp_path / 'data', launcher)
    yield service
    if not getattr(service, '_closed_by_controller', False):
        service.close()

@pytest.mark.parametrize('phrase,provider', [('play shape of you', 'spotify'), ('play shape of you on spotify', 'spotify'), ('play shape of you on youtube', 'youtube'), ('youtube play shape of you', 'youtube')])
def test_default_and_override(core, phrase, provider):
    core.save_settings(dict(core.app_settings(), default_music_player='spotify', spotify_open_mode='browser'))
    assert core.execute(phrase)['success']
    core.launcher.play_music.assert_called_once_with('shape of you', provider=provider, open_mode='browser')
    assert 'shape of you' not in json.dumps(core.history())

def test_spotify_independent_registration(core):
    youtube = next(c for c in core.commands() if c['target'] == 'https://www.youtube.com')
    core.save_command(youtube['name'], 'url', youtube['target'], youtube['phrases'], False, youtube['id'])
    assert core.execute('play example on spotify')['success']
    core.launcher.reset_mock()
    assert not core.execute('play example on youtube')['success']
    assert not core.launcher.mock_calls
    spotify = next(c for c in core.commands() if c['target'] == 'https://open.spotify.com')
    core.save_command(spotify['name'], 'url', spotify['target'], spotify['phrases'], False, spotify['id'])
    assert not core.execute('play example on spotify')['success']

@pytest.mark.parametrize('phrase', ['play', 'play song', 'play on spotify', 'play song on spotify'])
def test_empty_song(core, phrase):
    assert core.execute(phrase)['message'] == 'Please specify a song name.'
    assert not core.launcher.mock_calls

def test_deferred_worker(core, qtbot):
    core.save_settings(dict(core.app_settings(), default_music_player='spotify', spotify_open_mode='browser'))
    result = core.execute('play shape of you', defer_browser=True)
    assert not core.launcher.mock_calls
    worker = BrowserWorker(core.launcher, result['browser_action'], result['browser_target'], None,
                           result['music_provider'], result['music_open_mode'])
    received = []
    worker.completed.connect(lambda ok, message: received.append(ok))
    worker.run()
    assert received == [True]
    core.launcher.play_music.assert_called_once_with('shape of you', provider='spotify', open_mode='browser')

def test_legacy_parser_override():
    parsed = RuleBasedCommandParser().parse('play Shape of You on Spotify')
    assert parsed.target == 'shape of you' and parsed.parameters['provider'] == 'spotify'

def test_old_configuration_and_backup(core, tmp_path):
    old = core.export_configuration()
    old['settings'].pop('default_music_player')
    old['settings'].pop('spotify_open_mode')
    old['commands'] = []
    core.save_settings(dict(core.app_settings(), default_music_player='spotify'))
    core.import_configuration(old)
    assert core.app_settings()['default_music_player'] == 'youtube'
    core.db.execute("DELETE FROM app_settings WHERE key IN ('default_music_player', 'spotify_open_mode')")
    core.db.commit()
    backup = core.backup(tmp_path / 'old.db')
    core.save_settings(dict(core.app_settings(), default_music_player='spotify'))
    core.restore(backup)
    assert core.app_settings()['default_music_player'] == 'youtube'
    assert core.app_settings()['spotify_open_mode'] == 'auto'

def test_setting_persistence_and_validation(core):
    core.save_settings(dict(core.app_settings(), default_music_player='spotify'))
    assert core.get_setting('default_music_player') == 'spotify'
    with pytest.raises(ValueError):
        core.save_settings(dict(core.app_settings(), default_music_player='jiosaavn'))


def test_settings_controls_and_background_execution(qtbot, core, monkeypatch, tmp_path):
    from src.app.controller import ApplicationController
    from src.config.settings import settings
    from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    controller = ApplicationController(core)
    try:
        manager = controller.manager
        manager.navigate_to('Settings')
        combos = manager.findChildren(QComboBox)
        player = next(c for c in combos if c.findData('spotify') >= 0)
        mode = next(c for c in combos if c.findData('browser') >= 0)
        player.setCurrentIndex(player.findData('spotify'))
        mode.setCurrentIndex(mode.findData('browser'))
        save = next(b for b in manager.findChildren(QPushButton) if b.text() == 'Save preferences')
        save.click()
        assert core.app_settings()['default_music_player'] == 'spotify'
        assert core.app_settings()['spotify_open_mode'] == 'browser'
        controller.execute('play shape of you')
        qtbot.waitUntil(lambda: not controller._browser_workers, timeout=5000)
        core.launcher.play_music.assert_called_once_with('shape of you', provider='spotify', open_mode='browser')
        assert core.history()[0]['trigger_phrase'] == '[music playback]'
    finally:
        controller.shutdown()
        core._closed_by_controller = True
        controller.pet.hide()
        controller.manager.hide()
        QApplication.instance().aboutToQuit.disconnect(controller.shutdown)


def test_existing_database_upgrade_and_user_deletion(tmp_path):
    root = tmp_path / 'data'
    core = ApplicationCore(root, MagicMock())
    spotify = next(c for c in core.commands() if c['target'] == 'https://open.spotify.com')
    core.delete_command(spotify['id'])
    core.db.execute("DELETE FROM app_settings WHERE key='spotify_seeded'")
    core.db.commit()
    # A previous version may already have user-owned Spotify phrases.
    core.save_command('My Spotify shortcut', 'application', 'notepad', ['open spotify', 'spotify'])
    core.close()
    upgraded = ApplicationCore(root, MagicMock())
    spotify = next(c for c in upgraded.commands() if c['target'] == 'https://open.spotify.com')
    assert spotify['enabled']
    upgraded.delete_command(spotify['id'])
    upgraded.close()
    restarted = ApplicationCore(root, MagicMock())
    try:
        assert not any(c['target'] == 'https://open.spotify.com' for c in restarted.commands())
    finally:
        restarted.close()


@pytest.mark.parametrize('association', [1, 21, 18, None])
def test_spotify_detection_supports_store_activation(association):
    import ctypes

    def query(flags, kind, protocol, verb, buffer, size):
        assert flags == 0x1000 and protocol == 'spotify' and verb == 'open'
        if kind != association:
            return -2147023741  # No association of this kind.
        value = 'Spotify handler'
        if buffer is None:
            size._obj.value = len(value) + 1
            return 1  # S_FALSE: caller must allocate a buffer.
        buffer.value = value
        return 0

    function = MagicMock(side_effect=query)
    with patch('src.services.windows_launcher.os.name', 'nt'), patch.object(ctypes, 'WinDLL', create=True) as dll:
        dll.return_value.AssocQueryStringW = function
        assert WindowsLauncher.spotify_available() is (association is not None)
        assert [call.args[1] for call in function.call_args_list if call.args[4] is None] == (
            [1] if association == 1 else [1, 21] if association == 21 else [1, 21, 18])
