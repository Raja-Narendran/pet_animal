"""Handler for launching desktop applications."""
from .base import BaseCommandHandler
from ..model import Command, CommandResult, ActionType
from ...services.windows_launcher import BaseLauncher


class OpenApplicationHandler(BaseCommandHandler):
    """Executes OPEN_APPLICATION commands via the Windows launcher service."""

    def __init__(self, launcher: BaseLauncher):
        self.launcher = launcher

    def execute(self, command: Command) -> CommandResult:
        app_target = command.target.strip()
        success, message = self.launcher.open_application(app_target)
        
        return CommandResult(
            success=success,
            message=message,
            action=ActionType.OPEN_APPLICATION,
            target=app_target,
            pet_state="success" if success else "error",
        )
