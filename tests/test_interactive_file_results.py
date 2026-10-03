import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from src.core.application import ApplicationCore
from src.services.file_search import FileSearchService, FileSearchResponse, FileSearchResult
from src.services.recent_files import WindowsRecentItems, shortcut_target
from src.commands.interpreter.file_rules import file_intent
from src.config.settings import settings


def make_file(root, relative, modified):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('sample', encoding='utf-8')
    os.utime(path, (modified, modified))
    return str(path.resolve())


@pytest.fixture
def core(tmp_path, monkeypatch):
    root = tmp_path / 'files'
    root.mkdir()
    reader = MagicMock()
    reader.read.return_value = ({}, '')
    service = FileSearchService(roots=[root], recent_reader=reader)
    monkeypatch.setattr(service, '_everything_path', lambda: None)
    launcher = MagicMock()
    launcher.open_local_result.return_value = (True, 'Opening result')
    instance = ApplicationCore(tmp_path / 'data', launcher, file_search=service)
    yield instance
    instance.close()


def test_windows_and_pet_history_sorting_and_stable_clicks(core, tmp_path):
    old = make_file(tmp_path / 'files', 'old/report.xml', 1)
    newest = make_file(tmp_path / 'files', 'new/report.xml', 100)
    core.file_search.recent_reader.read.return_value = ({old: 200}, '')
    result = core.execute('/report.xml')
    assert result['search_sort'] == 'opened'
    assert result['file_results'][0]['path'] == old
    assert result['file_results'][0]['opened_source'] == 'Windows'
    identity = result['file_results'][0]['id']
    core.file_search.search = MagicMock(side_effect=AssertionError('sort must not search'))
    sorted_result = core.sort_file_results(result['search_token'], 'modified')
    assert sorted_result['file_results'][0]['path'] == newest
    opened = core.open_file_result(result['search_token'], identity)
    core.launcher.open_local_result.assert_called_once_with(old, is_folder=False)
    assert opened['file_results'] and core.file_open_records()[old] > 0
    assert core.file_session.response.results[core.file_session.selected].path == old


def test_recent_candidates_are_merged_before_cap_and_respect_scope(core, tmp_path):
    root = tmp_path / 'files'
    paths = [make_file(root, f'p{i}/report.xml', i + 10) for i in range(201)]
    recent = make_file(root, 'recent/report.xml', 1)
    outside = make_file(tmp_path / 'outside', 'report.xml', 300)
    core.file_search.local.search = MagicMock(return_value=FileSearchResponse(tuple(
        FileSearchResult(path, False, i + 10) for i, path in enumerate(paths[:200])), partial=True))
    core.file_search.recent_reader.read.return_value = ({recent: 900, outside: 1000}, '')
    result = core.execute('/report.xml')
    assert len(result['file_results']) == 200 and result['search_partial']
    assert result['file_results'][0]['path'] == recent
    assert outside not in [row['path'] for row in result['file_results']]


def test_pet_candidate_not_in_backend_and_duplicate_windows_record(core, tmp_path):
    recent = make_file(tmp_path / 'files', 'report.xml', 1)
    core.db.execute('INSERT INTO file_open_history VALUES (?,?)', (recent, 100))
    core.db.commit()
    core.file_search.local.search = MagicMock(return_value=FileSearchResponse())
    core.file_search.recent_reader.read.return_value = ({recent: 80}, '')
    result = core.execute('/report.xml')
    assert len(result['file_results']) == 1
    assert result['file_results'][0]['opened'] == 100
    assert result['file_results'][0]['opened_source'] == 'Pet'


def test_stale_and_expired_clicks_never_launch(core, tmp_path):
    make_file(tmp_path / 'files', 'report.xml', 1)
    result = core.execute('/report.xml')
    core.execute('/missing.xml')
    assert not core.open_file_result(result['search_token'], result['file_results'][0]['id'])['success']
    result = core.execute('/report.xml')
    core.file_session.created -= 301
    assert not core.open_file_result(result['search_token'], result['file_results'][0]['id'])['success']
    core.launcher.open_local_result.assert_not_called()


def test_failed_open_and_invalid_number_preserve_rows_without_history(core, tmp_path):
    make_file(tmp_path / 'files', 'report.xml', 1)
    result = core.execute('/report.xml')
    core.launcher.open_local_result.return_value = (False, 'File moved or deleted')
    failed = core.open_file_result(result['search_token'], result['file_results'][0]['id'])
    assert not failed['success'] and failed['file_results']
    assert not core.file_open_records()
    assert core.execute('open 99')['file_results']


def test_explicit_most_recent_still_means_modified(core, tmp_path):
    old = make_file(tmp_path / 'files', 'old/report.xml', 1)
    newest = make_file(tmp_path / 'files', 'new/report.xml', 100)
    core.file_search.recent_reader.read.return_value = ({old: 1000}, '')
    core.execute('/report.xml')
    core.execute('Open the most recent one')
    core.launcher.open_local_result.assert_called_once_with(newest, is_folder=False)


def test_history_persists_restart_and_version_five_backup_migrates(core, tmp_path):
    path = make_file(tmp_path / 'files', 'report.xml', 1)
    result = core.execute('/report.xml')
    core.open_file_result(result['search_token'], result['file_results'][0]['id'])
    backup = core.backup()
    restarted = ApplicationCore(tmp_path / 'data', MagicMock(), file_search=core.file_search)
    assert restarted.file_open_records()[path] > 0
    restarted.close()
    with sqlite3.connect(backup) as db:
        db.execute('DROP TABLE file_open_history')
        db.execute('PRAGMA user_version=5')
    before = backup.read_bytes()
    core.restore(backup)
    assert not core.file_open_records()
    assert core.db.execute('PRAGMA user_version').fetchone()[0] == 6
    assert backup.read_bytes() == before


def test_unavailable_recent_history_does_not_break_search(core, tmp_path):
    make_file(tmp_path / 'files', 'report.xml', 1)
    core.file_search.recent_reader.read.return_value = ({}, 'Windows recent activity is unavailable.')
    result = core.execute('/report.xml')
    assert result['file_results'][0]['opened'] is None
    assert 'unavailable' in result['message']


@pytest.fixture
def controller(core, qtbot, tmp_path, monkeypatch):
    from src.app.controller import ApplicationController
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    instance = ApplicationController(core)
    for widget in (instance.pet, instance.manager, instance.pet.response_bubble):
        qtbot.addWidget(widget)
    instance.manager.hide()
    instance.pet.show()
    yield instance
    core.listeners.clear()
    QApplication.instance().aboutToQuit.disconnect(instance.shutdown)
    # shutdown closes core; leave fixture closure idempotent by wrapping it here.
    instance.shutdown()
    core.close = lambda: None
    instance.pet.hide()
    instance.manager.hide()


def test_balloon_single_click_scroll_sort_and_keyboard(controller, tmp_path, qtbot):
    for i in range(8):
        make_file(tmp_path / 'files', f'project{i}/report.xml', i + 1)
    controller.submit('/report.xml')
    bubble = controller.pet.response_bubble
    qtbot.waitUntil(lambda: bubble.file_mode)
    assert bubble.suggestion_list.count() == 8
    assert bubble.suggestion_list.height() == 332
    assert bubble.auto_hide_timer.remainingTime() > 290000
    assert 'No recent-open record' in bubble.suggestion_list.item(0).text()
    assert bubble.suggestion_list.item(0).toolTip().startswith(str(tmp_path / 'files'))
    item = bubble.suggestion_list.item(2)
    target = controller.core.file_session.response.results[2].path
    qtbot.mouseClick(bubble.suggestion_list.viewport(), Qt.MouseButton.LeftButton,
        pos=bubble.suggestion_list.visualItemRect(item).center())
    controller.core.launcher.open_local_result.assert_called_once_with(target, is_folder=False)
    assert bubble.file_mode and bubble.suggestion_list.count() == 8
    qtbot.mouseClick(bubble.changed_button, Qt.MouseButton.LeftButton)
    assert controller.core.file_session.order == 'modified'
    field = controller.pet.command_box.input_field
    field.clear()
    controller.core.launcher.reset_mock()
    qtbot.keyClick(field, Qt.Key.Key_Down)
    selected = bubble.selected_file
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert controller.core.launcher.open_local_result.call_count == 1
    assert selected in [row['id'] for row in controller.core.file_session.present({})['file_results']]
    qtbot.keyClick(field, Qt.Key.Key_Escape)
    assert not bubble.isVisible() and not controller.core.file_session.active()


def test_empty_results_close_and_new_command_replace_balloon(controller, tmp_path, qtbot):
    controller.submit('/missing.xml')
    bubble = controller.pet.response_bubble
    qtbot.waitUntil(lambda: bubble.file_mode)
    assert not bubble.suggestion_list.count()
    qtbot.mouseClick(bubble.close_results_button, Qt.MouseButton.LeftButton)
    assert not bubble.isVisible()
    make_file(tmp_path / 'files', 'report.xml', 1)
    controller.submit('/report.xml')
    qtbot.waitUntil(lambda: bubble.file_mode)
    controller.submit('help')
    assert not bubble.file_mode and bubble.label.text().startswith('Commands:')


def test_native_shortcut_reader_getpath_without_execution(tmp_path):
    if os.name != 'nt':
        pytest.skip('Windows Shell API')
    import ctypes
    from src.services.recent_files import _guid, _method
    ole = ctypes.OleDLL('ole32')
    ole.CoInitializeEx(None, 2)
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    target = make_file(tmp_path, 'native.xml', 1)
    shortcut = tmp_path / 'native.lnk'
    try:
        clsid = _guid('00021401-0000-0000-c000-000000000046')
        iid = _guid('000214f9-0000-0000-c000-000000000046')
        ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(link))
        assert _method(link, 20, ctypes.HRESULT, ctypes.c_wchar_p)(link, target) == 0
        iid = _guid('0000010b-0000-0000-c000-000000000046')
        assert _method(link, 0, ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p)(link, ctypes.byref(iid), ctypes.byref(persist)) == 0
        assert _method(persist, 6, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_int)(persist, str(shortcut), 1) == 0
        assert shortcut_target(shortcut) == target
    finally:
        for pointer in (persist, link):
            if pointer:
                _method(pointer, 2, ctypes.c_ulong)(pointer)
        ole.CoUninitialize()


def test_balloon_long_unicode_paths_screen_edges_and_expiry(qtbot):
    from PyQt6.QtWidgets import QWidget
    from src.components.response import ResponseBubbleWidget
    owner = QWidget()
    qtbot.addWidget(owner)
    owner.resize(100, 100)
    owner.show()
    bubble = ResponseBubbleWidget(owner)
    qtbot.addWidget(bubble)
    path = 'D:/Projects/' + 'long-location-' * 15 + '/資料.xml'
    result = dict(message='Choose a result.', file_results=[dict(id='long', path=path,
        is_folder=False, modified=100, opened=None, opened_source=None)],
        search_token='edge', search_sort='opened', search_partial=False, search_remaining_ms=100)
    screen = QApplication.primaryScreen().availableGeometry()
    for corner in (screen.topLeft(), screen.bottomRight()):
        owner.move(corner)
        bubble.show_file_results(result)
        assert screen.contains(bubble.geometry())
        assert bubble.suggestion_list.item(0).toolTip().startswith(path)
    qtbot.waitUntil(lambda: not bubble.isVisible())
    assert not bubble.file_mode


def test_windows_reader_cancellation_and_malformed_link(tmp_path):
    import threading
    if os.name != 'nt':
        pytest.skip('Windows Shell API')
    cancel = threading.Event()
    cancel.set()
    records, notice = WindowsRecentItems().read(cancel=cancel)
    assert records == {}
    # A corrupt shortcut must not invoke anything or leave a COM object alive.
    invalid = tmp_path / 'invalid.lnk'
    invalid.write_bytes(b'not a shortcut')
    import ctypes
    ole = ctypes.OleDLL('ole32')
    ole.CoInitializeEx(None, 2)
    try:
        assert shortcut_target(invalid) is None
    finally:
        ole.CoUninitialize()
