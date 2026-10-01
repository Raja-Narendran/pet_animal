"""Extension point for interpreters, independent of validation and execution."""
from abc import ABC, abstractmethod
from .models import InterpretationResult


class IntentInterpreter(ABC):
    @abstractmethod
    def interpret(self, text: str) -> InterpretationResult:
        """Describe an intent without executing or saving anything."""
