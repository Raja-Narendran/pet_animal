"""Unit tests for CommandRegistry."""
from src.commands.registry import CommandRegistry
from src.commands.model import ActionType, Command, CommandResult
from src.commands.actions.base import BaseCommandHandler
from src.services.windows_launcher import BaseLauncher


class DummyLauncher(BaseLauncher):
    def open_application(self, app_key: str):
        return True, f"Opened {app_key}"

    def open_url(self, url: str):
        return True, f"Opened {url}"


class CustomTestHandler(BaseCommandHandler):
    def execute(self, command: Command) -> CommandResult:
        return CommandResult(
            success=True,
            message="Custom action handled",
            action=command.action,
        )


def test_registry_default_handlers():
    launcher = DummyLauncher()
    registry = CommandRegistry(launcher=launcher)

    assert registry.get_handler(ActionType.OPEN_APPLICATION) is not None
    assert registry.get_handler(ActionType.OPEN_URL) is not None
    assert registry.get_handler(ActionType.SHOW_HELP) is not None
    assert registry.get_handler(ActionType.UNKNOWN) is None


def test_registry_custom_handler():
    launcher = DummyLauncher()
    registry = CommandRegistry(launcher=launcher)
    custom_handler = CustomTestHandler()

    registry.register(ActionType.UNKNOWN, custom_handler)
    assert registry.get_handler(ActionType.UNKNOWN) is custom_handler
