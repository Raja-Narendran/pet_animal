"""Unit tests for WindowsLauncher security and dispatching."""
from unittest.mock import patch, MagicMock
import pytest
from src.services.windows_launcher import WindowsLauncher


def test_reject_unsupported_app():
    launcher = WindowsLauncher()
    success, msg = launcher.open_application("malicious_app")
    assert success is False
    assert "I don't know how to open 'malicious_app'" in msg


def test_reject_invalid_url_scheme():
    launcher = WindowsLauncher()
    success, msg = launcher.open_url("javascript:alert(1)")
    assert success is False
    assert "Invalid URL scheme" in msg

    success2, msg2 = launcher.open_url("file:///C:/evil.bat")
    assert success2 is False


@pytest.mark.parametrize("url", [
    "http://www.youtube.com",
    "https://example.org",
    "https://www.youtube.com.example.org",
    "https://www.youtube.com@evil.example",
])
@patch("webbrowser.open")
def test_reject_unlisted_url(mock_browser, url):
    success, _ = WindowsLauncher().open_url(url)
    assert success is False
    mock_browser.assert_not_called()


@patch("subprocess.Popen")
def test_open_notepad(mock_popen):
    launcher = WindowsLauncher()
    success, msg = launcher.open_application("notepad")
    assert success is True
    assert "Notepad" in msg
    mock_popen.assert_called_once_with(["notepad.exe"])


@patch("subprocess.Popen")
def test_open_calculator(mock_popen):
    launcher = WindowsLauncher()
    success, msg = launcher.open_application("calculator")
    assert success is True
    assert "Calculator" in msg
    mock_popen.assert_called_once_with(["calc.exe"])


@patch("subprocess.Popen")
def test_open_explorer(mock_popen):
    launcher = WindowsLauncher()
    success, msg = launcher.open_application("explorer")
    assert success is True
    assert "File Explorer" in msg
    mock_popen.assert_called_once_with(["explorer.exe"])


@patch("webbrowser.open")
def test_open_url_browser(mock_browser):
    mock_browser.return_value = True
    launcher = WindowsLauncher()
    success, msg = launcher.open_url("https://www.youtube.com")
    assert success is True
    assert "YouTube" in msg
    mock_browser.assert_called_once_with("https://www.youtube.com")


def test_vscode_not_found():
    launcher = WindowsLauncher()
    with patch.object(launcher, "find_vscode", return_value=None):
        success, msg = launcher.open_application("vscode")
        assert success is False
        assert "couldn't find Visual Studio Code" in msg
