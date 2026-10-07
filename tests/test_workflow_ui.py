"""Canvas editing, navigation, themes, progress and draft preservation."""
from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtWidgets import QApplication, QMessageBox
from src.app.controller import ApplicationController
from src.app.manager_window import PAGES
from src.core.application import ApplicationCore
from src.config.settings import settings


@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened')
    core = ApplicationCore(tmp_path / 'data', launcher)
    instance = ApplicationController(core)
    instance.show_manager('Workflows')
    yield instance
    core.listeners.clear()
    QApplication.instance().aboutToQuit.disconnect(instance.shutdown)
    instance.shutdown()
    instance.manager.hide()
    instance.pet.hide()
    instance.pet.response_bubble.close()


def fill(panel):
    panel.name.setText('Focus time')
    panel.phrases.setPlainText('focus now')
    panel.add_step()
    panel.type.setCurrentIndex(panel.type.findData('message'))
    panel.value.setText('Ready!')


def test_save_run_progress_and_step_settings(controller, qtbot):
    panel = controller.manager.workflows_panel
    assert PAGES[3] == 'Workflows'
    assert not hasattr(panel, 'add_type')
    fill(panel)
    assert panel.dirty and not panel.run_button.isEnabled()
    assert panel.save()
    assert panel.run_button.isEnabled()
    panel.run_button.click()
    qtbot.waitUntil(lambda: controller.last_workflow_result and controller.last_workflow_result.status == 'success')
    assert 'success' in panel.canvas.item(0).text()
    assert 'Ready!' in panel.progress.text()
    assert controller.pet.response_bubble.label.text() == 'Ready!'
    panel.type.setCurrentIndex(panel.type.findData('wait'))
    panel.seconds.setValue(90)
    assert panel.steps == [dict(type='wait', value=90)]
    assert panel.seconds.maximum() == 90
    panel.type.setCurrentIndex(panel.type.findData('message'))
    assert panel.value.maxLength() == 100
    assert panel.dirty and not panel.run_button.isEnabled()


def test_invalid_save_and_template_require_configuration(controller):
    panel = controller.manager.workflows_panel
    panel.template()
    assert len(panel.steps) == 6 and panel.steps[-1]['value'] == 'Ready!'
    assert panel.routine_id is None
    assert not panel.save()
    assert panel.notice.text()
    assert not controller.core.workflows.list()
    assert not controller.core.launcher.mock_calls


def test_reorder_buttons_and_internal_drag_model(controller):
    panel = controller.manager.workflows_panel
    fill(panel)
    panel.add_step()
    panel.type.setCurrentIndex(panel.type.findData('wait'))
    panel.seconds.setValue(2)
    panel.move_step(-1)
    assert [s['type'] for s in panel.steps] == ['wait', 'message']
    panel.move_step(1)
    assert [s['type'] for s in panel.steps] == ['message', 'wait']
    # Exercise the Qt model operation used by InternalMove drag/drop.
    assert panel.canvas.model().moveRow(QModelIndex(), 0, QModelIndex(), 2)
    assert [s['type'] for s in panel.steps] == ['wait', 'message']
    assert '1.' in panel.canvas.item(0).text()
    panel.remove_step()
    assert len(panel.steps) == 1


def test_draft_survives_core_notifications_and_theme(controller):
    panel = controller.manager.workflows_panel
    fill(panel)
    settings_payload = controller.core.app_settings()
    settings_payload['theme'] = 'dark'
    controller.core.save_settings(settings_payload)
    assert controller.manager.workflows_panel is panel
    assert panel.name.text() == 'Focus time' and panel.dirty
    assert panel.value.text() == 'Ready!'
    controller.core.confirm_name('Name changed')
    assert panel.steps == [dict(type='message', value='Ready!')]
    assert panel.dirty


def test_navigation_cancel_discard_and_save(controller, monkeypatch):
    panel = controller.manager.workflows_panel
    fill(panel)
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: QMessageBox.StandardButton.Cancel)
    controller.show_manager('Commands')
    assert controller.manager.page == 'Workflows'
    assert panel.dirty
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: QMessageBox.StandardButton.Save)
    controller.show_manager('Commands')
    assert controller.manager.page == 'Commands'
    rid = panel.routine_id
    controller.manager.open_workflow(rid)
    panel.name.setText('Discard this change')
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: QMessageBox.StandardButton.Discard)
    controller.show_manager('Activity')
    controller.show_manager('Workflows')
    assert panel.name.text() == 'Focus time' and not panel.dirty
    assert controller.core.workflows.get(rid)['name'] == 'Focus time'


def test_duplicate_search_and_enable_disable(controller):
    panel = controller.manager.workflows_panel
    fill(panel)
    assert panel.save()
    rid = panel.routine_id
    panel.search.setText('missing')
    assert panel.routines.count() == 0
    panel.search.setText('focus')
    assert panel.routines.count() == 1
    panel.toggle()
    assert not controller.core.workflows.get(rid)['enabled']
    panel.toggle()
    assert controller.core.workflows.get(rid)['enabled']
    panel.duplicate()
    assert panel.routine_id is None and panel.dirty
    assert panel.phrases.toPlainText() == ''
    assert not panel.enabled.isChecked()
    assert len(controller.core.workflows.list()) == 1


def test_running_editor_locked_stop_and_manager_hide(controller, qtbot):
    panel = controller.manager.workflows_panel
    fill(panel)
    panel.type.setCurrentIndex(panel.type.findData('wait'))
    panel.seconds.setValue(2)
    assert panel.save()
    panel.run()
    qtbot.waitUntil(controller._workflow_timer.isActive)
    assert not panel.editor.isEnabled()
    assert not panel.save_button.isEnabled()
    assert panel.stop_button.isEnabled()
    assert controller._workflow_timer.remainingTime() <= 2000
    controller.manager.close()
    assert controller.core.workflows.active is not None
    controller.show_manager('Workflows')
    panel.stop_button.click()
    assert controller.last_workflow_result.status == 'cancelled'
    assert panel.editor.isEnabled()
    assert not panel.stop_button.isEnabled()
    assert 'cancelled' in panel.progress.text()


def test_routine_commands_open_workflow_editor(controller):
    panel = controller.manager.workflows_panel
    fill(panel)
    assert panel.save()
    rid = panel.routine_id
    record = next(c for c in controller.core.commands() if c['target'] == rid)
    controller.show_manager('Commands')
    controller.manager.edit_command(record)
    assert controller.manager.page == 'Workflows'
    assert panel.routine_id == rid


def test_minimum_width_stacks_editor_and_preserves_draft(controller, qtbot):
    from PyQt6.QtWidgets import QBoxLayout
    panel = controller.manager.workflows_panel
    fill(panel)
    controller.manager.resize(850, 650)
    QApplication.processEvents()
    assert panel.compact
    assert panel.splitter.orientation() == Qt.Orientation.Vertical
    assert panel.body_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert panel.name.text() == 'Focus time' and panel.dirty
    controller.manager.resize(1200, 900)
    QApplication.processEvents()
    assert not panel.compact
    assert panel.steps[-1]['value'] == 'Ready!'


def fill_finance(panel, urls):
    panel.name.setText('finance')
    panel.phrases.setPlainText('trading')
    for url in urls:
        panel.add_step()
        panel.type.setCurrentIndex(panel.type.findData('url'))
        panel.value.setText(url)


@pytest.mark.parametrize('urls', [
    ('www.tradingview.com', 'www.moneycontrol.com'),
    ('tradingview.com/chart', 'moneycontrol.com?view=markets'),
    ('https://www.tradingview.com', 'https://www.moneycontrol.com'),
])
def test_finance_two_urls_save_button_persists_and_clears_unsaved_prompt(controller, monkeypatch, urls):
    panel = controller.manager.workflows_panel
    fill_finance(panel, urls)
    panel.save_button.click()
    assert panel.routine_id is not None
    assert not panel.dirty
    saved = controller.core.workflows.get(panel.routine_id)
    assert saved['name'] == 'finance' and saved['phrases'] == ['trading']
    assert saved['steps'] == [dict(type='url', value=url if url.startswith('https://') else 'https://' + url) for url in urls]
    assert panel.steps == saved['steps']
    assert panel.value.text() == saved['steps'][1]['value']
    assert 'Saved.' in panel.notice.text()
    assert panel.run_button.isEnabled()
    prompt = MagicMock(side_effect=AssertionError('A saved routine must not prompt for unsaved changes.'))
    monkeypatch.setattr(QMessageBox, 'question', prompt)
    controller.show_manager('Commands')
    assert controller.manager.page == 'Commands'
    assert not prompt.called
    controller.show_manager('Workflows')
    assert panel.routine_id == saved['id'] and not panel.dirty
    assert not controller.core.launcher.mock_calls


@pytest.mark.parametrize('url', ['http://example.com', 'javascript:alert(1)',
    'https://user:password@example.com', 'example.com:444', 'example.com/bad path', ''])
def test_invalid_url_save_shows_visible_error_and_keeps_draft(controller, qtbot, url):
    panel = controller.manager.workflows_panel
    fill_finance(panel, ('https://www.tradingview.com', url))
    panel.save_button.click()
    assert panel.routine_id is None and panel.dirty
    assert panel.steps[1]['value'] == url
    assert 'Step 2' in panel.notice.text()
    assert 'color:' in panel.notice.styleSheet()
    scroll = controller.manager.content_scroll
    qtbot.waitUntil(lambda: scroll.viewport().rect().contains(panel.notice.mapTo(scroll.viewport(), panel.notice.rect().center())))
    assert not controller.core.workflows.list()
    assert not controller.core.launcher.mock_calls


def test_url_error_is_beside_save_controls_and_clears_after_correction(controller, qtbot):
    panel = controller.manager.workflows_panel
    fill_finance(panel, ('www.tradingview.com', 'http://www.moneycontrol.com'))
    controller.manager.resize(850, 650)
    QApplication.processEvents()
    controller.manager.content_scroll.verticalScrollBar().setValue(controller.manager.content_scroll.verticalScrollBar().maximum())
    panel.save_button.click()
    qtbot.waitUntil(lambda: controller.manager.content_scroll.viewport().rect().contains(panel.notice.mapTo(controller.manager.content_scroll.viewport(), panel.notice.rect().center())))
    assert 'Step 2 (Open URL)' in panel.notice.text()
    assert panel.notice.parentWidget().layout().indexOf(panel.notice) == 1
    panel.value.setText('www.moneycontrol.com')
    panel.save_button.click()
    assert panel.routine_id and not panel.dirty
    assert panel.notice.styleSheet() == ''
    assert 'Saved.' in panel.notice.text()


def test_database_save_error_keeps_draft_and_explains_failure(controller, monkeypatch):
    import sqlite3
    panel = controller.manager.workflows_panel
    fill_finance(panel, ('www.tradingview.com', 'www.moneycontrol.com'))
    monkeypatch.setattr(controller.core.workflows, 'save', MagicMock(side_effect=sqlite3.OperationalError('database is locked')))
    panel.save_button.click()
    assert panel.routine_id is None and panel.dirty
    assert 'database is busy' in panel.notice.text()
    assert panel.name.text() == 'finance' and panel.phrases.toPlainText() == 'trading'
    assert panel.steps[1]['value'] == 'www.moneycontrol.com'


def test_open_file_picker_and_save(controller, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    panel = controller.manager.workflows_panel
    file = tmp_path / 'Finance notes.txt'
    file.touch()
    panel.name.setText('Finance files')
    panel.phrases.setPlainText('open trading notes')
    panel.add_step()
    index = panel.type.findData('file')
    assert index >= 0 and panel.type.itemText(index) == 'Open File'
    panel.type.setCurrentIndex(index)
    assert panel.type.currentData() == 'file'
    assert panel.browse.text() == 'Choose file…'
    assert 'default Windows app' in panel.file_hint.text()
    picker = MagicMock(return_value=(str(file), 'All files (*)'))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', picker)
    panel.browse.click()
    assert panel.value.text() == str(file)
    panel.save_button.click()
    assert not panel.dirty and panel.routine_id
    assert controller.core.workflows.get(panel.routine_id)['steps'] == [dict(type='file', value=str(file))]
    assert not controller.core.launcher.mock_calls


def test_cancel_file_picker_preserves_target(controller, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    panel = controller.manager.workflows_panel
    panel.add_step()
    panel.type.setCurrentIndex(panel.type.findData('file'))
    original = str(tmp_path / 'notes.txt')
    panel.value.setText(original)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *_: ('', ''))
    panel.browse.click()
    assert panel.value.text() == original
    assert panel.steps[0]['value'] == original
