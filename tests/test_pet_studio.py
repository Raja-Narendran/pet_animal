"""Unit tests for Manager Pet Studio UI and configuration."""
import os
import pytest
from PyQt6.QtWidgets import QApplication, QSlider, QSpinBox, QDoubleSpinBox, QLineEdit, QLabel
from PyQt6.QtCore import Qt
from src.core.application import ApplicationCore, DEFAULT_PET
from src.app.controller import ApplicationController
from src.services.windows_launcher import BaseLauncher


class DummyLauncher(BaseLauncher):
    def open_application(self, app_key: str):
        return True, "ok"

    def open_url(self, url: str):
        return True, "ok"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication([])
    return app


@pytest.fixture
def controller(tmp_path, qapp):
    core = ApplicationCore(tmp_path, launcher=DummyLauncher())
    ctrl = ApplicationController(core)
    yield ctrl
    core.listeners.clear()
    ctrl.pet.tray_icon.hide()
    ctrl.pet.hide()
    ctrl.manager.hide()
    qapp.aboutToQuit.disconnect(ctrl.shutdown)


def test_pet_studio_uses_sliders_and_omits_removed_fields(controller, qapp):
    manager = controller.manager
    manager.page = 'Pet Studio'
    manager.refresh()
    qapp.processEvents()

    # Find all QSliders
    sliders = manager.findChildren(QSlider)
    assert len(sliders) == 3, f"Expected 3 sliders, found {len(sliders)}"

    # Check slider ranges
    ranges = sorted([(s.minimum(), s.maximum()) for s in sliders])
    expected_ranges = sorted([(96, 400), (260, 600), (10, 24)])
    assert ranges == expected_ranges

    # Ensure removed controls do not exist in manager
    spin_boxes = manager.findChildren(QSpinBox)
    assert len(spin_boxes) == 0, f"Expected 0 QSpinBox in Pet Studio, found {len(spin_boxes)}"
    double_spin_boxes = manager.findChildren(QDoubleSpinBox)
    assert len(double_spin_boxes) == 0, f"Expected 0 QDoubleSpinBox in Pet Studio, found {len(double_spin_boxes)}"

    # Ensure no background line edit exists (only Pet Name should be a QLineEdit)
    line_edits = manager.findChildren(QLineEdit)
    assert len(line_edits) == 1, f"Expected 1 QLineEdit (Pet Name), found {len(line_edits)}"


def test_pet_studio_slider_value_labels_and_config(controller, qapp):
    manager = controller.manager
    manager.page = 'Pet Studio'
    manager.refresh()
    qapp.processEvents()

    sliders = manager.findChildren(QSlider)
    size_slider = next(s for s in sliders if s.minimum() == 96 and s.maximum() == 400)
    chat_slider = next(s for s in sliders if s.minimum() == 260 and s.maximum() == 600)
    text_slider = next(s for s in sliders if s.minimum() == 10 and s.maximum() == 24)

    # Change slider values
    size_slider.setValue(320)
    chat_slider.setValue(480)
    text_slider.setValue(18)
    qapp.processEvents()

    # Verify slider labels reflect numeric values without display units
    labels = [lbl.text() for lbl in manager.findChildren(QLabel)]
    assert "320" in labels
    assert "480" in labels
    assert "18" in labels

    # Set initial position on active profile to verify Option B position preservation
    active = controller.core.active_profile()
    controller.core.save_position(150, 250)

    # Save profile via manager's save logic by navigating through children buttons
    save_btns = [b for b in manager.findChildren(type(manager.centralWidget())) if b.objectName() == 'primary']
    # Trigger save & activate profile
    active_id = active['id']
    record = next(r for r in controller.core.profiles() if r['id'] == active_id)
    assert record['config']['x'] == 150
    assert record['config']['y'] == 250

    # Save & activate profile button
    buttons = manager.findChildren(type(manager.findChildren(QSlider)[0]))  # general check
    # Find button with text 'Save & activate profile'
    from PyQt6.QtWidgets import QPushButton
    save_btn = next(b for b in manager.findChildren(QPushButton) if b.text() == 'Save & activate profile')
    save_btn.click()
    qapp.processEvents()

    # Re-fetch profile and verify config
    updated = controller.core.active_profile()
    cfg = updated['config']
    assert cfg['size'] == 320
    assert cfg['chat_width'] == 480
    assert cfg['text_size'] == 18
    # Default values for removed options
    assert cfg['radius'] == DEFAULT_PET['radius']
    assert cfg['background'] == DEFAULT_PET['background']
    assert cfg['opacity'] == DEFAULT_PET['opacity']
    # Preserved position for Option B
    assert cfg['x'] == 150
    assert cfg['y'] == 250

    # Test saving as new profile resets x and y to None (default)
    new_btn = next(b for b in manager.findChildren(QPushButton) if b.text() == 'Save as new profile')
    # Change pet name so it's a distinct profile
    name_edit = manager.findChildren(QLineEdit)[0]
    name_edit.setText('New Pet')
    new_btn.click()
    qapp.processEvents()

    new_profile = next(p for p in controller.core.profiles() if p['name'] == 'New Pet')
    new_cfg = new_profile['config']
    assert new_cfg['size'] == 320
    assert new_cfg['chat_width'] == 480
    assert new_cfg['text_size'] == 18
    assert new_cfg['radius'] == DEFAULT_PET['radius']
    assert new_cfg['background'] == DEFAULT_PET['background']
    assert new_cfg['opacity'] == DEFAULT_PET['opacity']
    assert new_cfg['x'] is None
    assert new_cfg['y'] is None


def test_commands_table_row_selection_color(controller, qapp):
    from PyQt6.QtWidgets import QTableWidget
    from src.app.manager_window import PALETTES
    manager = controller.manager
    manager.page = 'Commands'
    manager.refresh()
    qapp.processEvents()

    table = manager.findChild(QTableWidget)
    assert table is not None
    assert table.rowCount() > 0

    # Verify stylesheet includes gray selection rules
    stylesheet = manager.styleSheet()
    assert 'selection-background-color:#D1D5DB' in stylesheet or 'selection-background-color:#4B5563' in stylesheet or 'QTableWidget::item:selected' in stylesheet

    # Select the first row
    table.selectRow(0)
    qapp.processEvents()
    assert table.currentRow() == 0
    assert len(table.selectedItems()) == table.columnCount()


def test_sidebar_and_general_settings(controller, qapp):
    from PyQt6.QtWidgets import QCheckBox, QComboBox, QPushButton
    manager = controller.manager
    qapp.processEvents()

    # Verify 'LOCAL FIRST' and 'Your data stays on this PC' are removed from all manager labels
    labels = [lbl.text() for lbl in manager.findChildren(QLabel)]
    assert not any('LOCAL FIRST' in text for text in labels)
    assert not any('Your data stays on this PC' in text for text in labels)

    # Navigate to Settings
    manager.page = 'Settings'
    manager.refresh()
    qapp.processEvents()

    # In Settings, the General card should only have theme, no QCheckBox widgets
    checkboxes = manager.findChildren(QCheckBox)
    assert len(checkboxes) == 0, f"Expected 0 QCheckBox in Settings, found {len(checkboxes)}"

    # Theme combobox should exist
    theme_box = next((c for c in manager.findChildren(QComboBox) if c.count() == 2 and 'light' in [c.itemText(i) for i in range(c.count())]), None)
    assert theme_box is not None
    assert theme_box.currentText() in ('light', 'dark')

    # Test saving theme preference
    target_theme = 'dark' if theme_box.currentText() == 'light' else 'light'
    theme_box.setCurrentText(target_theme)
    save_btn = next(b for b in manager.findChildren(QPushButton) if b.text() == 'Save preferences')
    save_btn.click()
    qapp.processEvents()

    assert controller.core.app_settings()['theme'] == target_theme


def test_dashboard_omits_quick_actions(controller, qapp):
    from PyQt6.QtWidgets import QLabel, QPushButton
    manager = controller.manager
    manager.page = 'Dashboard'
    manager.refresh()
    qapp.processEvents()

    labels = [lbl.text() for lbl in manager.findChildren(QLabel)]
    assert 'Quick actions' not in labels

    btn_texts = [btn.text() for btn in manager.findChildren(QPushButton)]
    assert 'Manage command phrases' not in btn_texts
    assert 'Customize your companion' not in btn_texts


def test_command_box_placeholder_text(controller, qapp):
    from src.components.command_box import CommandBoxWidget
    assert controller.pet.command_box.input_field.placeholderText() == "Hi!!"

    box = CommandBoxWidget()
    assert box.input_field.placeholderText() == "Hi!!"




