"""Base interface for action handlers."""
from abc import ABC, abstractmethod
from ..model import Command, CommandResult


class BaseCommandHandler(ABC):
    """Abstract base class for all command handlers."""

    @abstractmethod
    def execute(self, command: Command) -> CommandResult:
        """Executes the given normalized command and returns the result."""
        pass
