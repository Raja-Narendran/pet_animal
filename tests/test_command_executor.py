"""Unit tests for CommandExecutor."""
import pytest
from unittest.mock import MagicMock
from src.commands.executor import CommandExecutor
from src.commands.registry import CommandRegistry
from src.commands.model import Command, ActionType
from src.services.windows_launcher import BaseLauncher


@pytest.fixture
def mock_launcher():
    launcher = MagicMock(spec=BaseLauncher)
    launcher.open_application.return_value = (True, "Opening Chrome...")
    launcher.open_url.return_value = (True, "Opening YouTube...")
    return launcher


@pytest.fixture
def executor(mock_launcher):
    registry = CommandRegistry(launcher=mock_launcher)
    return CommandExecutor(registry=registry)


def test_execute_open_application(executor, mock_launcher):
    cmd = Command(action=ActionType.OPEN_APPLICATION, target="chrome")
    result = executor.execute(cmd)

    mock_launcher.open_application.assert_called_once_with("chrome")
    assert result.success is True
    assert result.action == ActionType.OPEN_APPLICATION
    assert "Opening Chrome" in result.message


def test_execute_open_url(executor, mock_launcher):
    cmd = Command(action=ActionType.OPEN_URL, target="https://www.youtube.com")
    result = executor.execute(cmd)

    mock_launcher.open_url.assert_called_once_with("https://www.youtube.com")
    assert result.success is True
    assert result.action == ActionType.OPEN_URL
    assert "Opening YouTube" in result.message


def test_execute_show_help(executor):
    cmd = Command(action=ActionType.SHOW_HELP)
    result = executor.execute(cmd)

    assert result.success is True
    assert result.action == ActionType.SHOW_HELP
    assert "open Chrome" in result.message
    assert "open Notepad" in result.message


def test_execute_empty_command(executor):
    cmd = Command(action=ActionType.EMPTY)
    result = executor.execute(cmd)

    assert result.success is False
    assert result.action == ActionType.EMPTY
    assert "Please type a command" in result.message


def test_execute_unknown_command(executor):
    cmd = Command(action=ActionType.UNKNOWN, target="something")
    result = executor.execute(cmd)

    assert result.success is False
    assert result.action == ActionType.UNKNOWN
    assert "I don't know that command" in result.message


def test_execute_application_failure(mock_launcher):
    mock_launcher.open_application.return_value = (
        False,
        "I couldn't find Visual Studio Code on this computer.",
    )
    registry = CommandRegistry(launcher=mock_launcher)
    executor = CommandExecutor(registry=registry)

    cmd = Command(action=ActionType.OPEN_APPLICATION, target="vscode")
    result = executor.execute(cmd)

    assert result.success is False
    assert "couldn't find" in result.message
    assert result.pet_state == "error"
