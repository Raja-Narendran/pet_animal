"""Handler for displaying help information."""
from .base import BaseCommandHandler
from ..model import Command, CommandResult, ActionType


class HelpHandler(BaseCommandHandler):
    """Executes SHOW_HELP commands, returning the supported desktop commands."""

    HELP_TEXT = (
        "Try:\n"
        "• open Chrome\n"
        "• open Notepad\n"
        "• open Calculator\n"
        "• open File Explorer\n"
        "• open VS Code\n"
        "• open YouTube\n"
        "• open Google"
    )

    def execute(self, command: Command) -> CommandResult:
        return CommandResult(
            success=True,
            message=self.HELP_TEXT,
            action=ActionType.SHOW_HELP,
            target="",
            pet_state="greeting",
        )
