"""Handler for opening web URLs in the default browser."""
from .base import BaseCommandHandler
from ..model import Command, CommandResult, ActionType
from ...services.windows_launcher import BaseLauncher


class OpenUrlHandler(BaseCommandHandler):
    """Executes OPEN_URL commands via the Windows launcher service."""

    def __init__(self, launcher: BaseLauncher):
        self.launcher = launcher

    def execute(self, command: Command) -> CommandResult:
        url_target = command.target.strip()
        success, message = self.launcher.open_url(url_target)
        
        return CommandResult(
            success=success,
            message=message,
            action=ActionType.OPEN_URL,
            target=url_target,
            pet_state="success" if success else "error",
        )
