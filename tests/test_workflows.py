"""Routine safety, storage and execution; all OS actions are mocked."""
import json
import sqlite3
import threading
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock
import pytest
from PyQt6.QtWidgets import QApplication
from src.core.application import ApplicationCore
from src.commands.interpreter import IntentType, MatchReason
from src.config.settings import settings
from src.app.controller import ApplicationController
from src.services.software_discovery import DiscoveredApplication, DiscoverySource


def step(kind, value):
    return dict(type=kind, value=value)


@pytest.fixture
def core(tmp_path):
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened')
    launcher.open_registered_url.return_value = (True, 'Opened')
    launcher.open_local_result.return_value = (True, 'Opened')
    service = ApplicationCore(tmp_path / 'data', launcher)
    yield service
    service.listeners.clear()
    if not getattr(service, "_closed_by_controller", False):
        service.close()


@pytest.fixture
def controller(core, qtbot, monkeypatch):
    monkeypatch.setattr(settings, 'STATE_FILE', core.root / 'state.json')
    instance = ApplicationController(core)
    instance.manager.hide()
    yield instance
    QApplication.instance().aboutToQuit.disconnect(instance.shutdown)
    instance.shutdown()
    core._closed_by_controller = True
    instance.manager.hide()
    instance.pet.hide()
    instance.pet.response_bubble.close()


def routine(core, steps=None, phrase='work setup', enabled=True):
    return core.workflows.save('Start Work', [phrase], steps if steps is not None else [step('message', 'Ready!')], enabled)


def finish_engine(core, engine):
    while engine.result.status == 'running':
        item = engine.begin_step()
        if item:
            engine.complete_step(True)
    core.workflows.finish()


def test_crud_restart_and_shared_phrase_conflicts(core):
    rid = routine(core)
    saved = core.workflows.get(rid)
    assert saved['steps'] == [step('message', 'Ready!')]
    assert core.interpret('  WORK   SETUP  ').intent.intent == IntentType.RUN_ROUTINE
    assert core.execute('work setup')['routine_id'] == rid
    assert not core.launcher.mock_calls
    with pytest.raises(ValueError, match='already registered'):
        core.save_command('Other', 'application', 'notepad', ['work setup'])
    with pytest.raises(ValueError):
        core.workflows.save('Other', ['open chrome'], saved['steps'])
    for phrase in ('help', 'what is my name', 'remember my name as Bob', 'do not work setup', '@chrome', '/folder'):
        with pytest.raises(ValueError):
            routine(core, phrase=phrase)
    assert core.interpret('do not work setup').reason == MatchReason.NEGATED_COMMAND
    assert not core.interpret('please start work').matched
    assert 'work setup' in core.execute('help')['message']
    duplicate = core.workflows.duplicate(rid)
    assert duplicate['phrases'] == [] and not duplicate['enabled']
    core.workflows.save('Updated', ['begin work'], saved['steps'], False, rid)
    assert core.interpret('begin work').reason == MatchReason.DISABLED_COMMAND
    removed = core.interpret('work setup')
    assert removed.matched and removed.intent.intent == IntentType.WEB_SEARCH
    assert removed.command_id != saved['command_id']
    second = ApplicationCore(core.root, MagicMock())
    try:
        assert second.workflows.get(rid)['name'] == 'Updated'
        assert not second.workflows.get(rid)['enabled']
    finally:
        second.close()
    core.workflows.delete(rid)
    assert not core.workflows.get(rid)
    assert not core.rows('SELECT id FROM commands WHERE id=?', (saved['command_id'],))


@pytest.mark.parametrize('steps', [[], [step('script', 'cmd.exe')], [step('application', 'cmd.exe')],
    [step('wait', -1)], [step('wait', 91)], [step('wait', True)], [step('wait', float('nan'))],
    [step('wait', float('inf'))], [step('message', '')], [step('message', 'x' * 101)],
    [step('message', 'a\nb')], [step('url', 'http://example.com')],
    [step('url', 'https://a:b@example.com')], [step('url', 'https://example.com:444')],
    [step('url', 'https://example.com/ bad')], [step('folder', 'relative')],
    [step('folder', r'\\server\share')], [dict(type='application', value='notepad', arguments='evil')],
    [step('message', 'ok')] * 51])
def test_invalid_step_payloads_are_transactional(core, steps):
    before = len(core.commands())
    with pytest.raises(ValueError):
        routine(core, steps)
    assert not core.workflows.list()
    assert len(core.commands()) == before


def test_limits_and_immutable_results(core):
    rid = routine(core, [step('wait', 90), step('message', 'x' * 100)])
    engine = core.workflows.start(rid)
    with pytest.raises(FrozenInstanceError):
        engine.result.status = 'bad'
    with pytest.raises(ValueError, match='already running'):
        core.workflows.start(rid)
    with pytest.raises(ValueError):
        core.workflows.delete(rid)
    with pytest.raises(ValueError):
        core.save_command('Changed', 'url', 'https://example.com', ['work setup'], command_id=core.workflows.get(rid)['command_id'])
    with pytest.raises(ValueError):
        core.import_configuration(core.export_configuration())
    backup = core.backup()
    with pytest.raises(ValueError):
        core.restore(backup)
    engine.begin_step()
    engine.cancel()
    core.workflows.finish()
    assert core.history()[0]['error_message'] == 'Routine cancelled.'
    assert core.rows('SELECT status FROM workflow_runs')[0]['status'] == 'cancelled'
    core.clear_history()
    assert not core.rows('SELECT * FROM workflow_runs')
    assert not core.rows('SELECT * FROM workflow_step_runs')


def test_all_steps_execute_sequentially_and_keep_history_private(controller, core, tmp_path, qtbot):
    url = 'https://dev.azure.com/private-project'
    folder = tmp_path / 'private-folder'
    folder.mkdir()
    steps = [step('application', 'vscode'), step('application', 'chrome'), step('url', url),
             step('folder', str(folder)), step('wait', .02), step('message', 'Ready!')]
    rid = routine(core, steps)
    result = controller.execute('work setup')
    assert result['success']
    qtbot.waitUntil(lambda: core.workflows.active is None, timeout=4000)
    assert core.launcher.mock_calls == [
        __import__('unittest.mock', fromlist=['call']).call.open_application('vscode'),
        __import__('unittest.mock', fromlist=['call']).call.open_application('chrome'),
        __import__('unittest.mock', fromlist=['call']).call.open_registered_url(url),
        __import__('unittest.mock', fromlist=['call']).call.open_local_result(str(folder), is_folder=True)]
    assert controller.pet.response_bubble.label.text() == 'Ready!'
    assert controller.last_workflow_result.status == 'success'
    assert all(s.status == 'success' for s in controller.last_workflow_result.steps)
    assert len(core.history()) == 1
    stored = json.dumps(core.rows('SELECT * FROM workflow_runs') + core.rows('SELECT * FROM workflow_step_runs') + core.history())
    for private in (url, str(folder), 'Ready!'):
        assert private not in stored
    assert core.history()[0]['trigger_phrase'] == 'work setup'
    assert core.rows('SELECT * FROM workflow_step_runs')[0]['started_at']


def test_preflight_stops_before_any_launch(controller, core, tmp_path):
    folder = tmp_path / 'gone'
    folder.mkdir()
    rid = routine(core, [step('application', 'notepad'), step('folder', str(folder))])
    folder.rmdir()
    reply = controller.start_routine(rid)
    assert not reply['success']
    assert not core.launcher.mock_calls
    assert [s.status for s in controller.last_workflow_result.steps] == ['skipped', 'failed']
    assert len(core.history()) == 1


def test_failure_skips_remaining_steps(controller, core, qtbot):
    core.launcher.open_application.return_value = (False, 'Raw private error')
    rid = routine(core, [step('application', 'notepad'), step('message', 'Wrong success')])
    controller.start_routine(rid)
    qtbot.waitUntil(lambda: core.workflows.active is None)
    assert [s.status for s in controller.last_workflow_result.steps] == ['failed', 'skipped']
    assert 'Step 1' in controller.last_workflow_result.message
    assert 'Raw private error' not in json.dumps(core.history() + core.rows('SELECT * FROM workflow_step_runs'))


def test_cancel_wait_and_stale_callback(controller, core, qtbot):
    rid = routine(core, [step('wait', 90), step('application', 'notepad')])
    controller.start_routine(rid)
    qtbot.waitUntil(controller._workflow_timer.isActive)
    token = core.workflows.active.result.id
    assert not controller.start_routine(rid)['success']
    controller.stop_routine()
    assert not controller._workflow_timer.isActive()
    controller._workflow_action_completed(token, True)
    assert not core.launcher.mock_calls
    assert [s.status for s in controller.last_workflow_result.steps] == ['cancelled', 'skipped']
    assert len(core.history()) == 1


def test_cancel_during_launcher_does_not_start_next_action(controller, core, qtbot):
    started, release = threading.Event(), threading.Event()
    def slow(_):
        started.set()
        release.wait(3)
        return True, 'Opened'
    core.launcher.open_application.side_effect = slow
    rid = routine(core, [step('application', 'notepad'), step('application', 'chrome')])
    try:
        controller.start_routine(rid)
        qtbot.waitUntil(started.is_set)
        controller.stop_routine()
        assert not controller.start_routine(rid)['success']
        release.set()
        qtbot.waitUntil(lambda: controller._workflow_worker is None)
        assert core.launcher.open_application.call_count == 1
        assert controller.last_workflow_result.status == 'cancelled'
        assert len(core.history()) == 1
    finally:
        release.set()


def test_live_registered_app_revalidation(controller, core, tmp_path, qtbot):
    executable = tmp_path / 'Editor.exe'
    executable.write_bytes(b'MZ')
    candidate = DiscoveredApplication.candidate('Editor', str(executable), DiscoverySource.START_MENU_USER)
    app_id = core.register_application(candidate, aliases=['test editor'], phrases=['open test editor'])
    rid = routine(core, [step('wait', .02), step('application', app_id)])
    controller.start_routine(rid)
    qtbot.waitUntil(controller._workflow_timer.isActive)
    core.set_application_enabled(app_id, False)
    qtbot.waitUntil(lambda: core.workflows.active is None)
    assert not core.launcher.open_application.called
    assert controller.last_workflow_result.steps[1].outcome == 'target_unavailable'


def workflow_payload(core):
    payload = core.export_configuration()
    payload['commands'] = [c for c in payload['commands'] if c['action_type'] == 'routine']
    return payload


def test_configuration_import_remaps_applications_and_disables_routines(core, tmp_path):
    executable = tmp_path / 'Editor.exe'
    executable.write_bytes(b'MZ')
    candidate = DiscoveredApplication.candidate('Editor', str(executable), DiscoverySource.START_MENU_USER)
    app_id = core.register_application(candidate, aliases=['test editor'], phrases=['open test editor'])
    routine(core, [step('application', app_id), step('message', 'Ready!')])
    payload = workflow_payload(core)
    executable.unlink()
    other = ApplicationCore(tmp_path / 'other', MagicMock())
    try:
        other.import_configuration(payload)
        imported = other.workflows.list()[0]
        assert not imported['enabled'] and 'unavailable' in imported['issues']
        assert imported['steps'][0]['value'] != app_id
        assert imported['steps'][0]['value'] == other.list_registered_applications()[0].id
        assert not other.execute('work setup')['success']
    finally:
        other.close()


def test_malformed_import_rolls_back_and_old_exports_work(core, tmp_path):
    routine(core)
    payload = workflow_payload(core)
    payload['routines'][0]['steps'] = [step('script', 'bad')]
    other = ApplicationCore(tmp_path / 'other', MagicMock())
    try:
        before = other.export_configuration()
        with pytest.raises(ValueError):
            other.import_configuration(payload)
        assert other.export_configuration() == before
        old = core.export_configuration()
        old.pop('routines')
        old['commands'] = []
        other.import_configuration(old)
        assert not other.workflows.list()
    finally:
        other.close()


def test_backup_restore_validates_routines_and_keeps_history(core):
    rid = routine(core)
    engine = core.workflows.start(rid)
    finish_engine(core, engine)
    backup = core.backup()
    core.workflows.delete(rid)
    core.restore(backup)
    assert core.workflows.get(rid)
    assert len(core.history()) == 1
    with sqlite3.connect(backup) as db:
        db.execute('UPDATE routines SET steps=?', (json.dumps([step('url', 'http://unsafe')]),))
    with pytest.raises(ValueError):
        core.restore(backup)
    assert core.workflows.get(rid)['steps'] == [step('message', 'Ready!')]


def test_version_six_migration_and_restore(core, tmp_path):
    backup = core.backup()
    with sqlite3.connect(backup) as db:
        for table in ('workflow_step_runs', 'workflow_runs', 'routines'):
            db.execute('DROP TABLE ' + table)
        db.execute('PRAGMA user_version=6')
    core.restore(backup)
    assert core.db.execute('PRAGMA user_version').fetchone()[0] == 7
    legacy = tmp_path / 'legacy' / 'database'
    legacy.mkdir(parents=True)
    import shutil
    shutil.copyfile(backup, legacy / 'petanimal.db')
    reopened = ApplicationCore(legacy.parent, MagicMock())
    try:
        assert reopened.db.execute('PRAGMA user_version').fetchone()[0] == 7
        assert reopened.commands()
    finally:
        reopened.close()


def test_interrupted_run_recovery(core):
    rid = routine(core)
    engine = core.workflows.start(rid)
    engine.begin_step()
    core.workflows.persist_progress()
    reopened = ApplicationCore(core.root, MagicMock())
    try:
        assert reopened.workflows.active is None
        assert reopened.rows('SELECT status FROM workflow_runs')[0]['status'] == 'cancelled'
        assert len(reopened.history()) == 1
    finally:
        reopened.close()
    # Simulate the crashed process rather than letting fixture shutdown finish again.
    core.workflows.active = None


def test_unavailable_routine_can_be_disabled_but_not_enabled(core, tmp_path):
    folder = tmp_path / 'temporary-project'
    folder.mkdir()
    rid = routine(core, [step('folder', str(folder))])
    folder.rmdir()
    core.workflows.set_enabled(rid, False)
    assert not core.workflows.get(rid)['enabled']
    with pytest.raises(ValueError):
        core.workflows.set_enabled(rid, True)
    assert not core.workflows.get(rid)['enabled']


def test_other_routines_can_be_saved_while_one_runs(core):
    rid = routine(core, [step('wait', 2)])
    engine = core.workflows.start(rid)
    other = core.workflows.save('Other routine', ['another setup'], [step('message', 'Other')])
    assert core.workflows.get(other)
    with pytest.raises(ValueError):
        core.workflows.set_enabled(rid, False)
    engine.cancel()
    core.workflows.finish()


def test_run_api_rejects_unregistered_trigger_without_history(core):
    rid = routine(core)
    with pytest.raises(ValueError):
        core.workflows.start(rid, 'private invalid input')
    assert not core.history()
    assert not core.rows('SELECT * FROM workflow_runs')


def test_open_file_uses_windows_default_association(controller, core, tmp_path, qtbot, monkeypatch):
    from src.services.windows_launcher import WindowsLauncher
    import os
    file = tmp_path / 'Trading notes.txt'
    file.write_text('Test document', encoding='utf-8')
    startfile = MagicMock()
    monkeypatch.setattr(os, 'startfile', startfile, raising=False)
    core.launcher = WindowsLauncher()
    rid = routine(core, [step('file', str(file)), step('message', 'Document ready')])
    controller.start_routine(rid)
    qtbot.waitUntil(lambda: core.workflows.active is None)
    assert controller.last_workflow_result.status == 'success'
    startfile.assert_called_once_with(str(file), 'open')
    assert core.rows('SELECT step_type FROM workflow_step_runs ORDER BY position')[0]['step_type'] == 'file'
    assert str(file) not in json.dumps(core.history() + core.rows('SELECT * FROM workflow_step_runs'))


def test_missing_file_stops_before_launching(controller, core, tmp_path):
    file = tmp_path / 'notes.txt'
    file.touch()
    rid = routine(core, [step('application', 'notepad'), step('file', str(file))])
    file.unlink()
    result = controller.start_routine(rid)
    assert not result['success'] and 'file is missing' in result['message']
    assert not core.launcher.mock_calls


def test_file_rechecked_after_wait(controller, core, tmp_path, qtbot):
    file = tmp_path / 'notes.txt'
    file.touch()
    rid = routine(core, [step('wait', .05), step('file', str(file))])
    controller.start_routine(rid)
    qtbot.waitUntil(controller._workflow_timer.isActive)
    file.unlink()
    qtbot.waitUntil(lambda: core.workflows.active is None)
    assert controller.last_workflow_result.status == 'failed'
    assert not core.launcher.open_local_result.called


@pytest.mark.parametrize('suffix', ['.exe', '.CMD', '.ps1', '.lnk', '.url', '.py', '.js'])
def test_file_steps_reject_executables_scripts_and_shortcuts(core, tmp_path, suffix):
    file = tmp_path / ('unsafe' + suffix)
    file.touch()
    with pytest.raises(ValueError, match='approved application'):
        routine(core, [step('file', str(file))])
    with pytest.raises(ValueError):
        core.workflows.validate_steps([step('file', str(file))], live=False)
    assert not core.workflows.list()


def test_file_step_rejects_folders_and_network_paths(core, tmp_path):
    for target in (str(tmp_path), r'\\server\share\notes.pdf', 'notes.pdf'):
        with pytest.raises(ValueError):
            routine(core, [step('file', target)])


def test_open_file_without_association_stops_routine(controller, core, tmp_path, qtbot, monkeypatch):
    from src.services.windows_launcher import WindowsLauncher
    import os
    file = tmp_path / 'notes.txt'
    file.touch()
    monkeypatch.setattr(os, 'startfile', MagicMock(side_effect=OSError('No associated app')), raising=False)
    core.launcher = WindowsLauncher()
    rid = routine(core, [step('file', str(file)), step('message', 'Should not appear')])
    controller.start_routine(rid)
    qtbot.waitUntil(lambda: core.workflows.active is None)
    assert [s.status for s in controller.last_workflow_result.steps] == ['failed', 'skipped']


def test_file_step_configuration_and_backup_round_trip(core, tmp_path):
    file = tmp_path / 'notes.txt'
    file.touch()
    rid = routine(core, [step('file', str(file))])
    backup = core.backup()
    core.workflows.delete(rid)
    core.restore(backup)
    assert core.workflows.get(rid)['steps'] == [step('file', str(file))]
    other = ApplicationCore(tmp_path / 'other', MagicMock())
    try:
        other.import_configuration(workflow_payload(core))
        imported = other.workflows.list()[0]
        assert imported['steps'] == [step('file', str(file))] and not imported['enabled']
    finally:
        other.close()
