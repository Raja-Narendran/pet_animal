"""Command execution engine."""
from typing import Optional
from .model import Command, CommandResult, ActionType
from .registry import CommandRegistry
from ..utils.logger import get_logger

logger = get_logger("executor")


class CommandExecutor:
    """Executes normalized commands using registered action handlers.
    
    Guarantees:
    - Never executes raw shell strings.
    - Never crashes on runtime exceptions.
    - Returns standardized CommandResult objects.
    """

    def __init__(self, registry: Optional[CommandRegistry] = None):
        self.registry = registry or CommandRegistry()

    def execute(self, command: Command) -> CommandResult:
        """Executes a parsed Command and returns the result."""
        logger.info(f"Executing command: action={command.action.value}, target='{command.target}'")

        if command.action == ActionType.EMPTY:
            return CommandResult(
                success=False,
                message="Please type a command!",
                action=ActionType.EMPTY,
                target="",
                pet_state="idle",
            )

        if command.action == ActionType.UNKNOWN:
            return CommandResult(
                success=False,
                message="I don't know that command yet.\nType 'help' to see what I can do.",
                action=ActionType.UNKNOWN,
                target=command.target,
                pet_state="error",
            )

        handler = self.registry.get_handler(command.action)
        if not handler:
            logger.error(f"No handler registered for action {command.action.value}")
            return CommandResult(
                success=False,
                message=f"No handler configured for action: {command.action.value}",
                action=command.action,
                target=command.target,
                pet_state="error",
            )

        try:
            result = handler.execute(command)
            logger.info(f"Command finished: success={result.success}, message='{result.message}'")
            return result
        except Exception as e:
            logger.exception(f"Unexpected exception during command execution: {e}")
            return CommandResult(
                success=False,
                message=f"Something went wrong: {e}",
                action=command.action,
                target=command.target,
                pet_state="error",
            )
