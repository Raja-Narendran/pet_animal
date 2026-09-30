"""Handler for searching the web in the default browser using Google."""
from .base import BaseCommandHandler
from ..model import Command, CommandResult, ActionType
from ...services.windows_launcher import BaseLauncher


class SearchWebHandler(BaseCommandHandler):
    """Executes SEARCH_WEB commands via the launcher service."""

    def __init__(self, launcher: BaseLauncher):
        self.launcher = launcher

    def execute(self, command: Command) -> CommandResult:
        query = command.target.strip()
        if not query:
            return CommandResult(
                success=False,
                message="What would you like me to search for?",
                action=ActionType.SEARCH_WEB,
                target="",
                pet_state="thinking",
            )

        success, message = self.launcher.search_web(query)
        return CommandResult(
            success=success,
            message=message,
            action=ActionType.SEARCH_WEB,
            target=query,
            pet_state="working" if success else "error",
        )
