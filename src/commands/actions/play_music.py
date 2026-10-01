"""Handler for searching and playing songs on YouTube."""
from .base import BaseCommandHandler
from ..model import Command, CommandResult, ActionType
from ...services.windows_launcher import BaseLauncher


class PlayMusicHandler(BaseCommandHandler):
    """Executes PLAY_MUSIC commands via the launcher service."""

    def __init__(self, launcher: BaseLauncher):
        self.launcher = launcher

    def execute(self, command: Command) -> CommandResult:
        song_name = command.target.strip()
        if not song_name:
            return CommandResult(
                success=False,
                message="What song would you like me to play?",
                action=ActionType.PLAY_MUSIC,
                target="",
                pet_state="thinking",
            )

        success, message = self.launcher.play_youtube(song_name)
        return CommandResult(
            success=success,
            message=message,
            action=ActionType.PLAY_MUSIC,
            target=song_name,
            pet_state="success" if success else "error",
        )
