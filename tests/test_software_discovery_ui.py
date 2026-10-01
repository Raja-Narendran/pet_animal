"""Approval dialogs, filtering and responsive background scan lifecycle."""
from dataclasses import replace
from unittest.mock import MagicMock
import time
import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QTextEdit
from src.app.manager_window import ManagerWindow
from src.core.application import ApplicationCore
from src.services.software_discovery import DiscoveredApplication, DiscoverySource, ApplicationValidator


@pytest.fixture
def manager(qtbot, tmp_path):
    core = ApplicationCore(tmp_path / 'data', MagicMock())
    window = ManagerWindow(core, MagicMock())
    window.navigation.setCurrentRow(2)
    qtbot.addWidget(window)
    yield window
    window.software_state.shutdown()
    core.listeners.clear()
    window.hide()
    core.close()


@pytest.fixture
def candidate(tmp_path):
    path = tmp_path / 'Spotify.exe'
    path.touch()
    return ApplicationValidator().validate(DiscoveredApplication.candidate('Spotify', str(path), DiscoverySource.START_MENU_USER, publisher='Spotify AB'))


def test_filtering_and_approval_cancel_then_save(manager, candidate, qtbot):
    state, panel = manager.software_state, manager.software_panel
    state.results = [candidate, ApplicationValidator().validate(replace(candidate, name='Missing', executable_path=candidate.executable_path + '.missing'))]
    state.updated.emit()
    assert panel.discovery_table.rowCount() == 2
    panel.search.setText('spotify ab')
    assert panel.discovery_table.rowCount() == 2  # Both share publisher.
    panel.search.setText('missing')
    assert panel.discovery_table.rowCount() == 1
    panel.discovery_table.selectRow(0)
    assert not panel.add_button.isEnabled()
    panel.search.clear()
    panel.filter_box.setCurrentText('Launchable')
    assert panel.discovery_table.rowCount() == 1
    panel.discovery_table.selectRow(0)
    assert panel.add_button.isEnabled()
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    panel.add_button.click()
    assert not manager.core.list_registered_applications()
    def approve():
        dialog = QApplication.activeModalWidget()
        # Approval allows editing the actual command phrases before saving.
        dialog.findChildren(QTextEdit)[1].setPlainText('music now\nopen spotify')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    QTimer.singleShot(0, approve)
    panel.add_button.click()
    assert len(manager.core.list_registered_applications()) == 1
    assert manager.core.interpret('music now').matched
    assert not manager.core.launcher.mock_calls
    manager.software_panel.filter_box.setCurrentText('Already Added')
    assert manager.software_panel.discovery_table.rowCount() == 1
    manager.software_panel.discovery_table.selectRow(0)
    assert not manager.software_panel.add_button.isEnabled()


def test_refresh_button_adds_valid_applications_without_blocking_navigation(manager, candidate, qtbot, monkeypatch):
    class SlowService:
        errors = []
        def discover(self, cancelled):
            for _ in range(20):
                if cancelled():
                    return []
                time.sleep(0.005)
            return [candidate]
    monkeypatch.setattr('src.app.software_discovery.SoftwareDiscoveryService', SlowService)
    manager.software_panel.refresh_button.click()
    worker = manager.software_state.worker
    manager.software_state.start()
    assert manager.software_state.worker is worker
    manager.navigation.setCurrentRow(0)
    assert manager.page == 'Dashboard'
    manager.navigation.setCurrentRow(2)
    assert not manager.software_panel.refresh_button.isEnabled()
    qtbot.waitUntil(lambda: not manager.software_state.busy)
    assert manager.software_panel.discovery_table.rowCount() == 1
    assert len(manager.core.list_registered_applications()) == 1
    assert manager.core.interpret('can you launch spotify').matched
    assert '1 added' in manager.software_state.message
    assert not manager.core.launcher.mock_calls
    manager.software_state.start()
    qtbot.waitUntil(lambda: not manager.software_state.busy)
    assert len(manager.core.list_registered_applications()) == 1
    assert '0 added' in manager.software_state.message


def test_worker_failure_and_shutdown(manager, qtbot, monkeypatch):
    class BrokenService:
        def discover(self, cancelled):
            raise OSError('private local path must not be displayed')
    monkeypatch.setattr('src.app.software_discovery.SoftwareDiscoveryService', BrokenService)
    manager.software_state.start()
    qtbot.waitUntil(lambda: not manager.software_state.busy)
    assert 'failed' in manager.software_state.message and 'private' not in manager.software_state.message
    class CancellableService:
        errors = []
        def discover(self, cancelled):
            while not cancelled():
                time.sleep(0.005)
            return []
    monkeypatch.setattr('src.app.software_discovery.SoftwareDiscoveryService', CancellableService)
    manager.software_state.start()
    worker = manager.software_state.worker
    manager.software_state.shutdown()
    assert not worker.isRunning() and not manager.software_state.busy
