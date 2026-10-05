"""Filename intent, offline backends, result conversations and opening boundaries."""
import csv
import os
import re
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from src.commands.interpreter import IntentType, RuleBasedIntentInterpreter
from src.commands.interpreter.file_rules import file_intent
from src.core.application import ApplicationCore
from src.services.file_search import (EverythingSearchBackend,
    FileSearchResponse, FileSearchResult, FileSearchService, LocalSearchBackend, is_local_path)
from src.services.windows_launcher import WindowsLauncher


def make_file(root, relative, modified=1000):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('test data', encoding='utf-8')
    os.utime(path, (modified, modified))
    return path.resolve()


@pytest.fixture
def core(tmp_path, monkeypatch):
    service = FileSearchService(roots=[tmp_path / 'files'])
    (tmp_path / 'files').mkdir()
    monkeypatch.setattr(service, '_everything_path', lambda: None)
    launcher = MagicMock()
    launcher.open_local_result.return_value = (True, 'Opened result')
    instance = ApplicationCore(tmp_path / 'data', launcher, file_search=service)
    yield instance
    instance.close()


def test_structured_intent_matches_requested_json_without_io(monkeypatch):
    monkeypatch.setattr(os, 'scandir', MagicMock(side_effect=AssertionError('parse performed I/O')))
    result = RuleBasedIntentInterpreter().interpret('Find PREPRODRELEASE.yml')
    assert result.intent.to_dict() == {'intent': 'FILE_SEARCH', 'query': 'PREPRODRELEASE.yml',
                                     'filters': {'extension': '.yml'}, 'action': 'FIND'}
    assert result.command_id is None


@pytest.mark.parametrize('phrase,query,folder', [
    ('/PREPRODRELEASE.yml', 'PREPRODRELEASE.yml', False),
    ('Find my package.xml', 'package.xml', False),
    ('Could you find My Report.XML?', 'Report.XML', False),
    ('Find pet folder', 'pet', True), ('/pet folder', 'pet', True),
    ('find folder Pet Animal', 'Pet Animal', True),
    ('search folders for PeTra', 'PeTra', True), ('search files for notes', 'notes', False),
    ('/"my folder"', 'my folder', False), ("/don't stop.txt", "don't stop.txt", False),
    ('/not.txt', 'not.txt', False), ('/சென்னை.txt', 'சென்னை.txt', False),
    ('/my notes.txt', 'my notes.txt', False), ('Find PREPRODRELEASE.yml.', 'PREPRODRELEASE.yml', False),
])
def test_shortcut_and_file_grammar_preserve_names(phrase, query, folder):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert result.matched and result.intent.intent == IntentType.FILE_SEARCH
    assert result.intent.query == query
    assert (dict(result.intent.filters).get('kind') == 'folder') == folder


@pytest.mark.parametrize('phrase', ['open player one', 'search Google for package.xml', 'remember my name as File',
    'open chrome', 'find Salesforce CI/CD', "don't find package.xml"])
def test_existing_commands_do_not_become_file_followups(phrase):
    result = RuleBasedIntentInterpreter().interpret(phrase)
    assert not result.intent or result.intent.intent != IntentType.FILE_SEARCH


def test_find_three_files_then_open_most_recent(core, tmp_path):
    paths = [make_file(tmp_path / 'files', f'project{index}/PREPRODRELEASE.yml', index + 1) for index in range(3)]
    result = core.execute('Find PREPRODRELEASE.yml')
    assert result['success'] and 'Found 3 files' in result['message']
    assert str(paths[-1]) in result['message']
    core.launcher.open_local_result.assert_not_called()
    assert core.execute('Open it.')['success']
    core.launcher.open_local_result.assert_called_once_with(str(paths[-1]), is_folder=False)
    assert not core.history()


def test_package_xml_salesforce_disambiguation(core, tmp_path):
    root = tmp_path / 'files'
    for index in range(11):
        make_file(root, f'project{index}/package.xml', index + 20)
    selected = make_file(root, 'Salesforce/manifest/package.xml', 1)
    result = core.execute('Find my package.xml')
    assert 'Found 12 files' in result['message'] and 'Salesforce project?' in result['message']
    assert not core.launcher.mock_calls
    assert core.execute('Yes.')['success']
    core.launcher.open_local_result.assert_called_once_with(str(selected), is_folder=False)


def test_salesforce_project_marker_and_explicit_recency(core, tmp_path):
    root = tmp_path / 'files'
    selected = make_file(root, 'CustomerCRM/manifest/package.xml', 1)
    make_file(root, 'CustomerCRM/sfdx-project.json')
    newest = make_file(root, 'other/package.xml', 50)
    assert 'Salesforce' in core.execute('/package.xml')['message']
    assert core.execute('Open the most recent one')['success']
    core.launcher.open_local_result.assert_called_once_with(str(newest), is_folder=False)
    core.launcher.reset_mock()
    core.execute('/package.xml')
    assert core.execute('the Salesforce one')['success']
    core.launcher.open_local_result.assert_called_once_with(str(selected), is_folder=False)


def test_unique_folder_shows_selection_and_file_with_same_name_is_separate(core, tmp_path):
    folder = tmp_path / 'files' / 'pet'
    folder.mkdir()
    make_file(tmp_path / 'files', 'other/pet')
    result = core.execute('Find pet folder')
    assert result['success'] and result['file_results'][0]['is_folder']
    assert not core.launcher.mock_calls
    assert core.open_file_result(result['search_token'], result['file_results'][0]['id'])['success']
    core.launcher.open_local_result.assert_called_once_with(str(folder), is_folder=True)
    core.launcher.reset_mock()
    assert core.execute('/pet')['success']
    assert not core.launcher.mock_calls
    assert core.execute('Open it')['success']
    assert core.launcher.open_local_result.call_args.kwargs == {'is_folder': False}


def test_ambiguous_folders_need_selection_and_number_is_snapshot(core, tmp_path):
    root = tmp_path / 'files'
    for name in ('a/pet', 'b/pet'):
        (root / name).mkdir(parents=True)
    core.execute('Find pet folder')
    assert not core.launcher.mock_calls
    results = core.file_session.response.results
    assert '1.' in core.execute('show results')['message']
    assert not core.execute('open 99')['success']
    assert core.execute('open result 2')['success']
    core.launcher.open_local_result.assert_called_once_with(results[1].path, is_folder=True)


def test_results_pagination_and_last_page(core, tmp_path):
    for index in range(12):
        make_file(tmp_path / 'files', f'p{index}/package.xml', index + 1)
    core.execute('/package.xml')
    assert '1.' in core.execute('show results')['message']
    assert '6.' in core.execute('next results')['message']
    assert '11.' in core.execute('next results')['message']
    assert '11.' in core.execute('next results')['message']
    assert '6.' in core.execute('previous results')['message']


@pytest.mark.parametrize('cancel', ['No', 'Cancel', "don't open it", 'help', 'unknown command', 'find missing.xml'])
def test_intervening_input_invalidates_previous_selection(core, tmp_path, cancel):
    make_file(tmp_path / 'files', 'package.xml')
    core.execute('/package.xml')
    core.execute(cancel)
    assert not core.execute('Open it')['success']
    assert not core.launcher.mock_calls


def test_confirmation_without_proposal_expiry_and_stale_worker(core, tmp_path):
    make_file(tmp_path / 'files', 'package.xml')
    core.execute('/package.xml')
    assert not core.execute('yes')['success']
    core.file_session.created -= 301
    assert not core.execute('open it')['success']
    first = core.execute('/package.xml', defer_file_search=True)
    second = core.execute('/other.xml', defer_file_search=True)
    response = core.file_search.search(first['file_search_intent'])
    assert core.finish_file_search(first['file_search_token'], first['file_search_intent'], response) is None
    core.execute('help')
    assert core.finish_file_search(second['file_search_token'], second['file_search_intent'], response) is None
    assert not core.launcher.mock_calls


def test_followup_while_searching_preserves_pending_query(core, tmp_path):
    make_file(tmp_path / 'files', 'package.xml')
    queued = core.execute('/package.xml', defer_file_search=True)
    waiting = core.execute('Open it')
    assert not waiting['success'] and 'still running' in waiting['message']
    assert core.file_session.token == queued['file_search_token']
    response = core.file_search.search(queued['file_search_intent'])
    assert core.finish_file_search(queued['file_search_token'], queued['file_search_intent'], response)['success']
    assert core.execute('Open it')['success']


def test_application_shortcut_invalidates_search_selection(core, tmp_path):
    make_file(tmp_path / 'files', 'package.xml')
    core.launcher.open_application.return_value = (True, 'Opened Notepad')
    core.execute('/package.xml')
    assert core.execute_application_shortcut('notepad')['success']
    assert not core.execute('Open it')['success']
    core.launcher.open_local_result.assert_not_called()


@pytest.mark.parametrize('phrase', ['/', '/folder', '/C:\\secret.txt', '/file*.xml', '/x\nopen chrome', '/' + 'a' * 501])
def test_invalid_shortcuts_cannot_open_or_launch_web_search(core, phrase):
    assert not core.execute(phrase)['success']
    assert not core.launcher.mock_calls


def test_partial_search_does_not_autopen_single_folder(core, tmp_path):
    folder = tmp_path / 'files' / 'pet'
    folder.mkdir()
    core.file_search.search = MagicMock(return_value=FileSearchResponse(
        (FileSearchResult(str(folder), True, 1),), partial=True))
    result = core.execute('find pet folder')
    assert 'at least 1' in result['message'] and 'incomplete' in result['message']
    assert not core.launcher.mock_calls


def test_local_search_extension_case_scope_and_recency(tmp_path):
    root = tmp_path / 'files'
    first = make_file(root, 'one/PREPRODRELEASE.yml', 1)
    second = make_file(root, 'two/preprodrelease.YML', 2)
    make_file(root, 'three/PREPRODRELEASE.yml.bak', 3)
    make_file(tmp_path, 'outside/PREPRODRELEASE.yml', 4)
    response = LocalSearchBackend().search('PREPRODRELEASE.yml', extension='.yml', roots=(root,))
    assert [item.path for item in response.results] == [str(second), str(first)]
    assert not response.partial


def test_local_scan_budget_cancellation_and_exclusions(tmp_path):
    root = tmp_path / 'files'
    make_file(root, 'one/package.xml')
    make_file(root, '.git/package.xml')
    response = LocalSearchBackend().search('package.xml', roots=(root,))
    assert len(response.results) == 1
    assert LocalSearchBackend(max_entries=0).search('package.xml', roots=(root,)).partial
    assert LocalSearchBackend(max_seconds=0).search('package.xml', roots=(root,)).partial
    cancel = threading.Event()
    cancel.set()
    assert LocalSearchBackend().search('package.xml', roots=(root,), cancel=cancel).partial


def test_permission_error_is_reported_as_partial(tmp_path, monkeypatch):
    def denied(path):
        raise PermissionError()
    monkeypatch.setattr(os, 'scandir', denied)
    response = LocalSearchBackend().search('package.xml', roots=(tmp_path,))
    assert response.partial and not response.results


@pytest.mark.parametrize('path', [r'\\server\share\file.xml', r'\\?\C:\file.xml', 'relative.xml', 'https://example.com/a.xml', 'C:\\file.xml\x00'])
def test_only_absolute_local_disk_paths_are_supported(path):
    assert not is_local_path(path)


def everything_mock(monkeypatch, executable, paths, returncode=0):
    def run(args, **kwargs):
        output = Path(args[args.index('-export-csv') + 1])
        with output.open('w', encoding='utf-8', newline='') as stream:
            csv.writer(stream).writerows([[str(path)] for path in paths])
        return subprocess.CompletedProcess(args, returncode, b'', b'')
    mocked = MagicMock(side_effect=run)
    monkeypatch.setattr(subprocess, 'run', mocked)
    return mocked


def test_everything_unicode_csv_literals_and_local_validation(tmp_path, monkeypatch):
    executable = make_file(tmp_path, 'es.exe')
    found = make_file(tmp_path, 'PeTra/சென்னை,release.yml', 30)
    other = make_file(tmp_path, 'other/சென்னை,release.yml', 1)
    run = everything_mock(monkeypatch, executable, [other, found, r'\\server\share\சென்னை,release.yml'])
    response = EverythingSearchBackend(executable).search('சென்னை,release.yml', extension='.yml')
    assert [item.path for item in response.results] == [str(found), str(other)]
    args = run.call_args.args[0]
    assert args[args.index('-regex') + 1] == re.escape('சென்னை,release.yml')
    assert run.call_args.kwargs['shell'] is False and run.call_args.kwargs['timeout'] == 4
    assert '/a-d' in args and '-sort' in args
    assert not Path(args[args.index('-export-csv') + 1]).exists()


def test_everything_scopes_and_folder_filter(tmp_path, monkeypatch):
    executable = make_file(tmp_path, 'es.exe')
    roots = (tmp_path / 'a', tmp_path / 'b')
    folders = [root / 'pet' for root in roots]
    for folder in folders:
        folder.mkdir(parents=True)
    run = everything_mock(monkeypatch, executable, folders)
    response = EverythingSearchBackend(executable).search('pet', folder=True, roots=roots)
    assert len(response.results) == 2
    args = run.call_args.args[0]
    assert '/ad' in args and '-match-path' in args
    pattern = args[args.index('-regex') + 1]
    assert all(re.search(pattern, str(folder)) for folder in folders)
    assert not re.search(pattern, str(tmp_path / 'outside/pet'))


@pytest.mark.parametrize('failure', [8, 7, 6, 'timeout', 'malformed'])
def test_everything_failures_use_local_fallback(tmp_path, monkeypatch, failure):
    executable = make_file(tmp_path, 'es.exe')
    selected = make_file(tmp_path, 'scope/package.xml')
    def run(args, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(args, 4)
        if failure == 'malformed':
            Path(args[args.index('-export-csv') + 1]).write_text('bad,csv,row')
            return subprocess.CompletedProcess(args, 0, b'', b'')
        return subprocess.CompletedProcess(args, failure, b'', b'')
    monkeypatch.setattr(subprocess, 'run', run)
    service = FileSearchService(roots=[tmp_path / 'scope'], everything_executable=str(executable))
    result = service.search(file_intent('/package.xml'))
    assert result.backend == 'local' and result.results[0].path == str(selected)
    assert 'Everything is unavailable' in result.notice


def test_everything_empty_success_is_not_a_backend_failure(tmp_path, monkeypatch):
    executable = make_file(tmp_path, 'es.exe')
    everything_mock(monkeypatch, executable, [])
    local = MagicMock()
    service = FileSearchService(roots=[tmp_path], everything_executable=str(executable), local_backend=local)
    response = service.search(file_intent('/missing.xml'))
    assert not response.results and response.backend == 'Everything'
    local.search.assert_not_called()


def test_search_configuration_persists_and_reloads(core, tmp_path):
    root = tmp_path / 'files'
    core.save_file_search_settings([str(root)])
    assert core.file_search_settings()['roots'] == [str(root)]
    assert core.file_search.roots == (root,)
    assert core.export_configuration()['file_search'] == core.file_search_settings()
    backup = core.backup()
    core.save_file_search_settings([])
    core.restore(backup)
    assert core.file_search_settings()['roots'] == [str(root)]
    assert core.file_search.roots == (root,)


@pytest.mark.parametrize('phrase', ['/package.xml', 'find pet folder', 'Open it', 'Yes', 'the Salesforce one'])
def test_search_phrases_are_reserved(core, phrase):
    with pytest.raises(ValueError, match='reserved'):
        core.save_command('Hijack search', 'application', 'notepad', [phrase])


@pytest.mark.parametrize('extension', ['.exe', '.cmd', '.bat', '.ps1', '.lnk', '.url', '.js', '.py', '.reg', '.msi'])
def test_search_cannot_bypass_application_allowlist(tmp_path, monkeypatch, extension):
    path = make_file(tmp_path, 'unsafe' + extension)
    opening = MagicMock()
    monkeypatch.setattr(os, 'startfile', opening, raising=False)
    assert not WindowsLauncher().open_local_result(str(path))[0]
    opening.assert_not_called()


def test_document_and_folder_opening_recheck_types_and_deleted_paths(tmp_path, monkeypatch, caplog):
    file = make_file(tmp_path, 'private-document-234.yml')
    folder = tmp_path / 'pet'
    folder.mkdir()
    opening = MagicMock()
    monkeypatch.setattr(os, 'startfile', opening, raising=False)
    launcher = WindowsLauncher()
    assert not launcher.open_local_result(str(file), is_folder=True)[0]
    assert not launcher.open_local_result(str(folder), is_folder=False)[0]
    assert launcher.open_local_result(str(file))[0]
    opening.assert_called_once_with(str(file), 'open')
    assert file.name not in caplog.text and str(file) not in caplog.text
    file.unlink()
    assert not launcher.open_local_result(str(file))[0]


def test_only_successfully_opened_paths_persist_outside_command_history(core, tmp_path):
    selected = make_file(tmp_path / 'files', 'private-report-234.xml')
    core.execute('/private-report-234.xml')
    assert selected.name not in '\n'.join(core.db.iterdump())
    core.execute('Open it')
    core.execute('help')
    assert not core.history()
    assert core.file_open_records().keys() == {str(selected)}
    assert core.db.execute('SELECT count(*) FROM file_open_history').fetchone()[0] == 1


def test_response_wraps_long_paths_and_keeps_original_tooltip(qtbot):
    from src.components.response import ResponseBubbleWidget
    bubble = ResponseBubbleWidget()
    qtbot.addWidget(bubble)
    message = r'Found 3 files. The most recent one is in D:\Projects\PeTra_CICD_Pipelines\templates\PREPRODRELEASE.yml.'
    bubble.show_message(message, wrap_paths=True)
    assert '\u200b' in bubble.label.text()
    assert bubble.label.text().replace('\u200b', '') == message
    assert bubble.label.toolTip() == message
    bubble.show_message('Ready')
    assert bubble.label.text() == 'Ready' and not bubble.label.toolTip()


def test_controller_search_is_asynchronous_and_stale_results_are_ignored(qtbot, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from src.app.controller import ApplicationController
    from src.config.settings import settings
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    started, release = threading.Event(), threading.Event()
    selected = make_file(tmp_path, 'package.xml')
    main_thread = threading.get_ident()
    def search(intent, cancel=None):
        assert threading.get_ident() != main_thread
        started.set()
        release.wait(2)
        return FileSearchResponse((FileSearchResult(str(selected), False, 1),))
    service = MagicMock()
    service.search.side_effect = search
    core = ApplicationCore(tmp_path / 'data', MagicMock(), file_search=service)
    controller = ApplicationController(core)
    try:
        controller.submit('/package.xml')
        qtbot.waitUntil(started.is_set)
        assert controller._file_workers
        assert 'Searching local files' in controller.pet.response_bubble.label.text()
        controller.submit('help')
        release.set()
        qtbot.waitUntil(lambda: not controller._file_workers)
        assert controller.pet.response_bubble.label.text().startswith('Commands:')
        assert not core.file_session.active()
        controller.manager.navigation.setCurrentRow(__import__('src.app.manager_window', fromlist=['PAGES']).PAGES.index('Settings'))
        assert controller.manager.findChildren(__import__('PyQt6.QtWidgets', fromlist=['QPlainTextEdit']).QPlainTextEdit)
    finally:
        release.set()
        controller.shutdown()
        controller.pet.hide()
        controller.manager.hide()
        QApplication.instance().aboutToQuit.disconnect(controller.shutdown)
