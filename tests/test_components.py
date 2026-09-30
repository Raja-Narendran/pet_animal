"""Unit tests for UI components and integration."""
import os
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent
from src.components.command_box import CommandBoxWidget
from src.components.response import ResponseBubbleWidget
from src.components.pet import PetWidget
from src.app.pet_window import PetWindow
from src.commands.parser import RuleBasedCommandParser
from src.commands.executor import CommandExecutor
from src.services.windows_launcher import BaseLauncher


class MockLauncher(BaseLauncher):
    def __init__(self):
        self.launched_apps = []
        self.launched_urls = []

    def open_application(self, app_key: str):
        self.launched_apps.append(app_key)
        return True, f"Mock Opening {app_key}..."

    def open_url(self, url: str):
        self.launched_urls.append(url)
        return True, f"Mock Opening {url}..."


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication([])
    return app


def test_command_box_submission(qapp):
    box = CommandBoxWidget()
    submitted = []
    box.command_submitted.connect(lambda cmd: submitted.append(cmd))

    box.input_field.setText("open notepad")
    box.send_button.click()

    assert submitted == ["open notepad"]
    assert box.input_field.text() == ""  # Cleared after submit


def test_response_bubble_display(qapp):
    bubble = ResponseBubbleWidget()
    bubble.show_message("Test message", timeout_ms=0)
    assert bubble.isVisible()
    assert bubble.label.text() == "Test message"


def test_pet_window_command_flow(qapp):
    mock_launcher = MockLauncher()
    from src.commands.registry import CommandRegistry

    registry = CommandRegistry(launcher=mock_launcher)
    executor = CommandExecutor(registry=registry)
    parser = RuleBasedCommandParser()

    win = PetWindow(parser=parser, executor=executor)
    win.show()
    
    # Simulate submitting command
    win.command_box.input_field.setText("open calculator")
    win.command_box.send_button.click()

    assert "calculator" in mock_launcher.launched_apps
    assert "Mock Opening calculator" in win.response_bubble.label.text()


def test_pet_window_toggle_command_box(qapp):
    win = PetWindow()
    win.show()
    # Initial state is visible
    assert not win.command_box.isHidden()

    # Click pet toggles it hidden
    win.pet.pet_clicked.emit()
    assert win.command_box.isHidden()

    # Click pet again toggles it visible
    win.pet.pet_clicked.emit()
    assert not win.command_box.isHidden()


def test_default_position_keeps_complete_window_on_screen(qapp, monkeypatch, tmp_path):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "STATE_FILE", tmp_path / "missing.json")
    win = PetWindow()
    try:
        win.show()
        qapp.processEvents()
        assert qapp.primaryScreen().availableGeometry().contains(win.geometry())
    finally:
        win.tray_icon.hide()
        win.close()


def test_help_expansion_stays_on_screen(qapp, monkeypatch, tmp_path):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "STATE_FILE", tmp_path / "missing.json")
    win = PetWindow()
    try:
        win.show()
        qapp.processEvents()
        geom = qapp.primaryScreen().availableGeometry()
        win.move(geom.right() - win.width() + 1, geom.bottom() - win.height() + 1)
        win.show_help()
        qapp.processEvents()
        assert geom.contains(win.geometry())
    finally:
        win.tray_icon.hide()
        win.close()


def test_unreadable_state_does_not_prevent_startup(qapp, monkeypatch, tmp_path):
    from src.config.settings import settings

    # Opening a directory as a JSON file raises an OSError on Windows and POSIX.
    monkeypatch.setattr(settings, "STATE_FILE", tmp_path)
    win = PetWindow()
    try:
        win.show()
        qapp.processEvents()
        assert win._read_saved_state() is None
        assert qapp.primaryScreen().availableGeometry().contains(win.geometry())
    finally:
        win.tray_icon.hide()
        win.close()
