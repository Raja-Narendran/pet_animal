"""Application shortcut catalog, live authorization, and balloon interaction regressions."""
import json
from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import QObject, QEvent, QPoint, Qt
from PyQt6.QtWidgets import QApplication
from src.app.controller import ApplicationController
from src.config.settings import settings
from src.core.application import ApplicationCore
from src.services.software_discovery import DiscoveredApplication, DiscoverySource


@pytest.fixture
def core(tmp_path):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened application')
    instance = ApplicationCore(tmp_path / 'data', launcher)
    yield instance
    instance.close()


def add_app(core, tmp_path, name='Spotify', alias='spotify', command=True):
    executable = tmp_path / (alias.replace(' ', '-') + '.exe')
    executable.write_bytes(b'MZ')
    candidate = DiscoveredApplication.candidate(name, str(executable), DiscoverySource.START_MENU_USER)
    target = core.register_application(candidate, aliases=[alias],
        phrases=['open ' + alias] if command else None)
    return target, executable


def targets(core, query=''):
    return [entry.target for entry in core.application_shortcuts(query)]


def test_catalog_is_read_only_and_contains_only_apps(core):
    before = core.db.total_changes
    entries = core.application_shortcuts()
    assert [entry.display_name for entry in entries] == ['Calculator', 'Chrome', 'File Explorer', 'Notepad', 'VS Code']
    assert set(targets(core)) == {'chrome', 'notepad', 'calculator', 'explorer', 'vscode'}
    assert not core.application_shortcuts('youtube')
    assert core.db.total_changes == before and not core.history()
    assert not core.launcher.mock_calls


@pytest.mark.parametrize('query,expected', [('CH', 'chrome'), ('GOOGLE CHROME', 'chrome'),
    ('note pad', 'notepad'), ('studio', 'vscode'), ('EXPLORER', 'explorer')])
def test_name_alias_prefix_and_substring_matching(core, query, expected):
    assert targets(core, query) == [expected]


@pytest.mark.parametrize('query', ['unknown', 'chrome\n', 'x' * 501, None])
def test_catalog_rejects_unmatched_and_invalid_queries(core, query):
    assert not core.application_shortcuts(query)
    assert not core.history() and not core.launcher.mock_calls


def test_ranking_and_live_rename(core, tmp_path):
    substring, _ = add_app(core, tmp_path, 'My Spotify', 'player one')
    prefix, _ = add_app(core, tmp_path, 'Spotify Studio', 'player two')
    exact, _ = add_app(core, tmp_path, 'Spotify', 'player three')
    assert targets(core, 'spotify') == [exact, prefix, substring]
    core.update_application(exact, 'Music Player', ['music player'])
    assert targets(core, 'music player') == [exact]
    assert targets(core, 'spotify') == [prefix, substring]


def test_duplicate_app_names_keep_distinct_target_ids(core, tmp_path):
    first, _ = add_app(core, tmp_path, 'Music Player', 'player one')
    second, _ = add_app(core, tmp_path, 'Music Player', 'player two')
    assert set(targets(core, 'Music Player')) == {first, second}
    assert not core.execute('@Music Player')['success']
    assert not core.launcher.mock_calls
    assert core.execute_application_shortcut(second)['success']
    core.launcher.open_application.assert_called_once_with(second)


def test_grouping_and_deterministic_command_choice(core):
    builtin = next(command for command in core.commands() if command['target'] == 'notepad')
    core.save_command('Z notes', 'application', 'notepad', ['write notes'])
    core.save_command('A notes', 'application', 'notepad', ['notes now'])
    assert targets(core).count('notepad') == 1
    assert core.execute_application_shortcut('notepad')['success']
    assert core.history()[0]['command_id'] == builtin['id']
    core.save_command(builtin['name'], 'application', 'notepad', builtin['phrases'], False, builtin['id'])
    assert core.execute_application_shortcut('notepad')['success']
    chosen = next(command for command in core.commands() if command['name'] == 'A notes')
    assert core.history()[0]['command_id'] == chosen['id']
    assert core.history()[0]['trigger_phrase'] == 'notes now'


def test_registered_app_requires_an_enabled_command(core, tmp_path):
    target, _ = add_app(core, tmp_path, command=False)
    assert target not in targets(core)
    assert not core.execute_application_shortcut(target)['success']
    core.save_command('My music', 'application', target, ['music now'])
    assert targets(core, 'spotify') == [target]
    assert core.execute_application_shortcut(target)['success']
    core.launcher.open_application.assert_called_once_with(target)


@pytest.mark.parametrize('change', ['disable app', 'repair', 'remove app', 'disable command',
    'delete command', 'missing executable', 'unsafe executable', 'unsafe command'])
def test_stale_suggestions_never_bypass_live_authorization(core, tmp_path, change):
    target, executable = add_app(core, tmp_path)
    command = next(command for command in core.commands() if command['target'] == target)
    assert targets(core, 'spotify') == [target]
    if change == 'disable app':
        core.set_application_enabled(target, False)
    elif change == 'repair':
        with core.db:
            core.db.execute('UPDATE registered_applications SET needs_repair=1 WHERE id=?', (target,))
    elif change == 'remove app':
        core.unregister_application(target)
    elif change == 'disable command':
        core.save_command(command['name'], 'application', target, command['phrases'], False, command['id'])
    elif change == 'delete command':
        core.delete_command(command['id'])
    elif change == 'missing executable':
        executable.unlink()
    elif change == 'unsafe executable':
        unsafe = tmp_path / 'cmd.exe'
        unsafe.write_bytes(b'MZ')
        with core.db:
            core.db.execute('UPDATE registered_applications SET executable_path=? WHERE id=?', (str(unsafe), target))
    else:
        with core.db:
            core.db.execute('UPDATE commands SET action_config=? WHERE id=?',
                (json.dumps({'target': 'cmd /c calc.exe'}), command['id']))
    assert not core.execute_application_shortcut(target)['success']
    assert not core.launcher.mock_calls
    assert len(core.history()) == 1
    assert core.history()[0]['trigger_phrase'] in ('open spotify', '[unsupported command]')
    assert str(executable) not in json.dumps(core.history())


def test_dispatch_rechecks_target_after_catalog_resolution(core, monkeypatch):
    entries = core.application_shortcuts()
    entry = next(item for item in entries if item.target == 'chrome')
    monkeypatch.setattr(core, 'application_shortcuts', lambda query='': entries)
    with core.db:
        core.db.execute('UPDATE commands SET action_config=? WHERE id=?',
            (json.dumps({'target': 'calculator'}), entry.command_id))
    assert not core.execute_application_shortcut('chrome')['success']
    assert not core.launcher.mock_calls


@pytest.mark.parametrize('phrase', ['@chrome & calc', '@C:/secret/private.exe', '@unknown private value'])
def test_unresolved_shortcuts_keep_history_private(core, phrase):
    assert not core.execute(phrase)['success']
    assert core.history()[0]['trigger_phrase'] == '[unsupported command]'
    assert phrase not in json.dumps(core.history()) and not core.launcher.mock_calls


def test_exact_shortcut_uses_existing_execution_and_canonical_history(core):
    assert core.execute('  @Google Chrome  ')['success']
    core.launcher.open_application.assert_called_once_with('chrome')
    assert len(core.history()) == 1 and core.history()[0]['trigger_phrase'] == 'open chrome'


def test_qt_events_before_pet_construction_are_safe():
    controller = ApplicationController.__new__(ApplicationController)
    QObject.__init__(controller)
    assert not controller.eventFilter(QObject(), QEvent(QEvent.Type.Show))


@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened application')
    core = ApplicationCore(tmp_path / 'ui-data', launcher)
    instance = ApplicationController(core)
    for widget in (instance.pet, instance.manager, instance.pet.response_bubble):
        qtbot.addWidget(widget)
    instance.manager.hide()
    instance.pet.show()
    instance.pet.activateWindow()
    instance.pet.command_box.input_field.setFocus()
    QApplication.processEvents()
    yield instance
    core.listeners.clear()
    QApplication.instance().aboutToQuit.disconnect(instance.shutdown)
    instance.shutdown()
    instance.pet.hide()
    instance.manager.hide()
    instance.pet.response_bubble.close()


def test_typing_filters_without_launching_and_keeps_focus(controller, qtbot):
    field, bubble = controller.pet.command_box.input_field, controller.pet.response_bubble
    qtbot.keyClicks(field, '@')
    assert bubble.isVisible() and bubble.suggestion_list.count() == 5
    assert bubble.selected_application == 'calculator'
    assert field.hasFocus() and not bubble.auto_hide_timer.isActive()
    qtbot.keyClicks(field, 'ch')
    assert bubble.selected_application == 'chrome' and bubble.suggestion_list.count() == 1
    assert field.hasFocus() and not controller.core.history()
    assert not controller.core.launcher.mock_calls


@pytest.mark.parametrize('submit', ['enter', 'send', 'click'])
def test_partial_shortcut_submission_opens_once_and_shows_result(controller, qtbot, submit):
    field, bubble = controller.pet.command_box.input_field, controller.pet.response_bubble
    qtbot.keyClicks(field, '@ch')
    if submit == 'enter':
        qtbot.keyClick(field, Qt.Key.Key_Return)
    elif submit == 'send':
        qtbot.mouseClick(controller.pet.command_box.send_button, Qt.MouseButton.LeftButton)
    else:
        item = bubble.suggestion_list.item(0)
        qtbot.mouseClick(bubble.suggestion_list.viewport(), Qt.MouseButton.LeftButton,
            pos=bubble.suggestion_list.visualItemRect(item).center())
    controller.core.launcher.open_application.assert_called_once_with('chrome')
    assert len(controller.core.history()) == 1
    assert controller.core.history()[0]['trigger_phrase'] == 'open chrome'
    assert not field.text() and bubble.isVisible() and not bubble.suggestion_mode
    assert bubble.label.text() == 'Opened application' and bubble.auto_hide_timer.isActive()
    bubble.application_selected.emit('chrome')  # A queued second click cannot repeat a launch.
    assert controller.core.launcher.open_application.call_count == 1


def test_arrow_selection_and_escape_until_next_edit(controller, qtbot):
    field, bubble = controller.pet.command_box.input_field, controller.pet.response_bubble
    qtbot.keyClicks(field, '@')
    qtbot.keyClick(field, Qt.Key.Key_Down)
    assert bubble.selected_application == 'chrome'
    qtbot.keyClick(field, Qt.Key.Key_Up)
    assert bubble.selected_application == 'calculator'
    qtbot.keyClick(field, Qt.Key.Key_Escape)
    assert not bubble.isVisible() and field.text() == '@'
    controller.core.changed()
    assert not bubble.isVisible()
    qtbot.keyClicks(field, 'c')
    assert bubble.isVisible()
    qtbot.keyClick(field, Qt.Key.Key_Down)
    qtbot.keyClick(field, Qt.Key.Key_Return)
    controller.core.launcher.open_application.assert_called_once_with('chrome')


def test_no_matches_and_normal_chat_behavior(controller, qtbot):
    field, bubble = controller.pet.command_box.input_field, controller.pet.response_bubble
    field.setText('ch')
    assert not bubble.isVisible()
    field.setText('@unknown private value')
    assert bubble.isVisible() and not bubble.suggestion_list.count()
    assert bubble.label.text() == 'No matching apps. Add apps in Commands.'
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert controller.core.history()[0]['trigger_phrase'] == '[unsupported command]'
    assert not controller.core.launcher.mock_calls and not bubble.suggestion_mode
    field.setText('open notepad')
    qtbot.keyClick(field, Qt.Key.Key_Return)
    controller.core.launcher.open_application.assert_called_once_with('notepad')
    assert bubble.isVisible() and bubble.label.text() == 'Opened application'


def test_live_registration_disable_remove_and_scroll(controller, tmp_path, qtbot):
    field, bubble, core = controller.pet.command_box.input_field, controller.pet.response_bubble, controller.core
    field.setText('@')
    added = [add_app(core, tmp_path, 'Player ' + str(index), 'player ' + str(index))[0] for index in range(3)]
    assert bubble.suggestion_list.count() == 8
    assert bubble.suggestion_list.height() == 194
    qtbot.waitUntil(lambda: bubble.suggestion_list.verticalScrollBar().maximum() > 0)
    field.setText('@player 1')
    assert bubble.selected_application == added[1]
    core.update_application(added[1], 'Renamed Player', ['renamed player'])
    # The still-registered "open player 1" phrase remains an alias after renaming.
    assert bubble.suggestion_list.item(0).text() == 'Renamed Player'
    field.setText('@renamed')
    assert bubble.selected_application == added[1]
    core.set_application_enabled(added[1], False)
    assert not bubble.suggestion_list.count()
    core.set_application_enabled(added[1], True)
    assert bubble.selected_application == added[1]
    core.unregister_application(added[1])
    assert not bubble.suggestion_list.count()
    assert not core.history() and not core.launcher.mock_calls


def test_duplicate_names_are_identifiable_and_click_target_id(controller, tmp_path, qtbot):
    first, _ = add_app(controller.core, tmp_path, 'Music Player', 'player one')
    second, _ = add_app(controller.core, tmp_path, 'Music Player', 'player two')
    controller.pet.command_box.input_field.setText('@Music Player')
    listing = controller.pet.response_bubble.suggestion_list
    assert listing.count() == 2 and listing.item(0).text() != listing.item(1).text()
    item = next(listing.item(index) for index in range(2)
        if listing.item(index).data(Qt.ItemDataRole.UserRole) == second)
    qtbot.mouseClick(listing.viewport(), Qt.MouseButton.LeftButton, pos=listing.visualItemRect(item).center())
    controller.core.launcher.open_application.assert_called_once_with(second)


def test_balloon_tracks_pet_and_minimized_chat_without_moving_owner(controller, qtbot):
    pet, field, bubble = controller.pet, controller.pet.command_box.input_field, controller.pet.response_bubble
    pet.move(250, 350)
    QApplication.processEvents()
    owner_position, pet_position = pet.pos(), pet.pet.mapToGlobal(QPoint())
    field.setText('@')
    assert pet.pos() == owner_position and pet.pet.mapToGlobal(QPoint()) == pet_position
    first = bubble.pos()
    pet.move(pet.pos() + QPoint(30, 20))
    assert bubble.pos() == first + QPoint(30, 20)
    controller.minimize_pet()
    assert pet.pet_minimized and bubble.isVisible() and bubble.suggestion_mode
    assert bubble.y() + bubble.height() <= field.mapToGlobal(QPoint()).y()
    field.setText('@ch')
    qtbot.keyClick(field, Qt.Key.Key_Return)
    controller.core.launcher.open_application.assert_called_once_with('chrome')
    assert bubble.isVisible() and not pet.pet.isVisible()
    controller.restore_pet()
    field.setText('@')
    screen = QApplication.primaryScreen().availableGeometry()
    pet.move(screen.topLeft())
    assert screen.contains(bubble.frameGeometry())
    field.hide()
    assert not bubble.isVisible()
    field.show()
    field.setText('@ch')
    controller.hide_pet()
    assert not bubble.isVisible()
