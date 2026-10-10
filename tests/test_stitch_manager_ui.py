"""Behavioral regressions for the native Stitch Manager migration."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import MagicMock
import hashlib
import json
import pytest
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import QApplication, QPushButton, QBoxLayout, QLabel
from src.app.controller import ApplicationController
from src.app.manager_window import PAGES
from src.app.manager_ui import theme
from src.app.manager_ui.preview import SpritePreview
from src.config.settings import settings
from src.core.application import ApplicationCore

@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'STATE_FILE', tmp_path / 'state.json')
    launcher = MagicMock()
    launcher.open_application.return_value = (True, 'Opened')
    core = ApplicationCore(tmp_path / 'data', launcher)
    instance = ApplicationController(core)
    yield instance
    core.listeners.clear()
    QApplication.instance().aboutToQuit.disconnect(instance.shutdown)
    instance.shutdown()
    instance.manager.hide()
    instance.pet.hide()
    instance.pet.response_bubble.close()

def click(manager, text):
    next(b for b in manager.findChildren(QPushButton) if b.text() == text and b.isVisibleTo(manager)).click()


@pytest.mark.parametrize('page, button_text', [
    ('Dashboard', 'New command'),
    ('Memory', 'Add memory'),
    ('Commands', 'New command'),
    ('Workflows', 'Stop'),
    ('Pet Studio', 'Import PNG sheet'),
    ('Activity', 'Clear history'),
])
@pytest.mark.parametrize('width,height', [(1600, 1000), (850, 650)])
def test_page_header_actions_align_with_right_content_edge(controller, page, button_text, width, height):
    manager = controller.manager
    manager.resize(width, height)
    controller.show_manager(page)
    QApplication.processEvents()
    action = next(b for b in manager.findChildren(QPushButton)
                  if b.text() == button_text and b.isVisibleTo(manager))
    action_right = action.mapTo(manager.content, QPoint(action.width() - 1, 0)).x()
    assert manager.content.width() - 60 <= action_right <= manager.content.width()

def test_dashboard_activity_link_opens_activity(controller):
    manager = controller.manager
    click(manager, 'View all activity')
    assert manager.page == 'Activity'
    assert controller.core.app_settings()['page'] == 'Activity'


def test_dashboard_omits_sensitive_records_windows_dpapi_phrase(controller):
    manager = controller.manager
    controller.show_manager('Dashboard')
    QApplication.processEvents()
    labels = [lbl.text() for lbl in manager.findChildren(QLabel)]
    assert not any('sensitive records' in t for t in labels)
    assert not any('Windows DPAPI' in t for t in labels)

def test_command_filters_and_toggle_use_existing_service(controller):
    manager = controller.manager
    controller.show_manager('Commands')
    manager.command_search.setText('notepad')
    assert manager.command_table.rowCount() == 1
    record = manager.command_records[0]
    manager.command_table.cellWidget(0, 4).setChecked(False)
    assert not next(c for c in controller.core.commands() if c['id'] == record['id'])['enabled']
    assert manager.command_search.text() == 'notepad'
    manager.command_states.setCurrentIndex(manager.command_states.findData(True))
    assert manager.command_table.rowCount() == 0
    assert not controller.core.launcher.mock_calls

def test_routine_command_toggle_uses_routine_enablement(controller):
    rid = controller.core.workflows.save('Morning', ['morning now'], [dict(type='message', value='Ready')])
    controller.show_manager('Commands')
    manager = controller.manager
    manager.command_types.setCurrentIndex(manager.command_types.findData('routine'))
    assert manager.command_table.rowCount() == 1
    manager.command_table.cellWidget(0, 4).setChecked(False)
    assert not controller.core.workflows.get(rid)['enabled']

def test_command_row_edit_retains_record_identity_after_filter(controller, monkeypatch):
    controller.show_manager('Commands')
    manager = controller.manager
    manager.command_search.setText('notepad')
    expected = manager.command_records[0]['id']
    seen = []
    monkeypatch.setattr(manager, 'edit_command', lambda record: seen.append(record['id']))
    # Refill constructs actions with the current handler, then selects the matching row.
    manager.command_search.setText('open notepad')
    tools = manager.command_table.cellWidget(0, 5)
    next(b for b in tools.findChildren(QPushButton) if b.toolTip() == 'Edit command').click()
    assert seen == [expected]

def test_memory_refresh_remasks_and_preserves_selection(controller):
    core = controller.core
    cat = next(c['id'] for c in core.categories() if c['sensitive'])
    mid = core.memory_service.create_memory(cat, 'Private sample', 'private.sample', 'fixture-secret')
    controller.show_manager('Memory')
    manager = controller.manager
    manager.memory_table.selectRow(next(i for i,r in enumerate(manager.memory_records) if r['id'] == mid))
    manager.reveal_memory_value(mid)
    assert manager.memory_detail_value.toPlainText() == 'fixture-secret'
    manager.refresh()
    assert manager.memory_selected_id == mid
    assert manager.memory_detail_value.toPlainText() == '••••••••'
    assert not manager.memory_value_revealed

def test_page_subscriptions_do_not_accumulate(controller):
    manager = controller.manager
    baseline = controller.receivers(controller.voice_hotkey_status_changed)
    for _ in range(5):
        controller.show_manager('Settings')
        assert controller.receivers(controller.voice_hotkey_status_changed) == baseline + 1
        controller.show_manager('Commands')
        assert manager.software_state.receivers(manager.software_state.updated) == 1
        controller.show_manager('Dashboard')
        assert controller.receivers(controller.voice_hotkey_status_changed) == baseline
        assert manager.software_state.receivers(manager.software_state.updated) == 0

def test_preview_timer_stops_on_navigation(controller):
    controller.show_manager('Pet Studio')
    QApplication.processEvents()
    manager = controller.manager
    preview = manager.findChild(SpritePreview)
    assert preview.timer.isActive()
    controller.show_manager('Dashboard')
    assert not preview.timer.isActive()

@pytest.mark.parametrize('page', PAGES)
@pytest.mark.parametrize('size', [(850,650), (1200,900), (1600,1000)])
def test_pages_fit_window_without_horizontal_overflow(controller, qtbot, page, size):
    manager = controller.manager
    manager.resize(*size)
    controller.show_manager(page)
    QApplication.processEvents()
    assert (manager.width(), manager.height()) == size
    assert manager.content_scroll.horizontalScrollBar().maximum() == 0
    if size[0] < 1100:
        assert all(row.box.direction() == QBoxLayout.Direction.TopToBottom for row in manager.responsive_rows)

def test_local_assets_have_verified_hashes_and_font_fallback(monkeypatch, tmp_path):
    for entry in json.loads((settings.BASE_DIR/'assets/ui/stitch/sources.json').read_text()):
        assert hashlib.sha256((settings.BASE_DIR/entry['path']).read_bytes()).hexdigest() == entry['sha256']
    assert theme.load_font() == 'Inter'
    monkeypatch.setattr(theme, '_font_family', None)
    monkeypatch.setattr(settings, 'BASE_DIR', tmp_path)
    assert theme.load_font() == 'Segoe UI'

def test_preview_pauses_when_manager_hidden_and_resumes(controller):
    controller.show_manager('Pet Studio')
    QApplication.processEvents()
    preview = controller.manager.findChild(SpritePreview)
    assert preview.timer.isActive()
    controller.manager.hide()
    assert not preview.timer.isActive()
    controller.manager.show()
    QApplication.processEvents()
    assert preview.timer.isActive()

def test_switch_keyboard_input_preserves_command_behavior(controller, qtbot):
    controller.show_manager('Commands')
    manager = controller.manager
    manager.command_search.setText('notepad')
    control = manager.command_table.cellWidget(0, 4)
    control.setFocus()
    qtbot.keyClick(control, Qt.Key.Key_Space)
    assert not manager.command_records[0]['enabled']
    assert not controller.core.launcher.mock_calls


def test_selected_command_actions_follow_filtered_record(controller):
    core = controller.core
    core.workflows.save('Morning', ['morning now'], [dict(type='message', value='Ready')])
    controller.show_manager('Commands')
    manager = controller.manager
    assert not any(b.isEnabled() for b in manager.command_action_buttons)
    manager.command_search.setText('notepad')
    manager.command_table.selectRow(0)
    assert not manager.command_workflow_button.isEnabled()
    assert manager.command_action_buttons[0].isEnabled()
    manager.command_search.setText('morning')
    assert not any(b.isEnabled() for b in manager.command_action_buttons)
    manager.command_table.selectRow(0)
    assert manager.command_workflow_button.isEnabled()
    manager.command_search.setText('no matching record')
    assert not any(b.isEnabled() for b in manager.command_action_buttons)


def test_long_text_and_empty_filters_fit_compact_view(controller, qtbot):
    core = controller.core
    category = next(c['id'] for c in core.categories() if not c['sensitive'])
    mid = core.memory_service.create_memory(category, 'Long title ' * 13, 'sample.long', 'Long value ' * 100)
    controller.manager.resize(850, 650)
    controller.show_manager('Memory')
    manager = controller.manager
    manager.memory_table.selectRow(next(i for i,r in enumerate(manager.memory_records) if r['id'] == mid))
    QApplication.processEvents()
    assert manager.content_scroll.horizontalScrollBar().maximum() == 0
    assert manager.memory_detail_value.toPlainText() == core.get_memory(mid)['memory_value']
    manager.memory_search.setText('no matching record')
    QApplication.processEvents()
    assert manager.memory_table.rowCount() == 0
    assert manager.content_scroll.horizontalScrollBar().maximum() == 0


def test_missing_icon_degrades_to_empty_native_icon(monkeypatch, tmp_path):
    from src.app.manager_ui.icons import icon
    icon.cache_clear()
    monkeypatch.setattr(settings, 'BASE_DIR', tmp_path)
    assert icon('unavailable-fixture-icon').isNull()
    icon.cache_clear()


def test_hidden_studio_refresh_keeps_preview_timer_stopped(controller):
    manager = controller.manager
    controller.show_manager('Pet Studio')
    QApplication.processEvents()
    manager.hide()
    manager.refresh()
    QApplication.processEvents()
    assert all(not p.timer.isActive() for p in manager.findChildren(SpritePreview))
    manager.show()
    QApplication.processEvents()
    current = next(p for p in manager.findChildren(SpritePreview) if p.isVisible())
    assert current.timer.isActive()
