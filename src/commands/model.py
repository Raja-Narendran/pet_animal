"""Normalized Command and Result data models."""
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any


class ActionType(str, Enum):
    """Normalized action types supported by the desktop companion."""
    OPEN_APPLICATION = "OPEN_APPLICATION"
    OPEN_URL = "OPEN_URL"
    SHOW_HELP = "SHOW_HELP"
    EMPTY = "EMPTY"
    UNKNOWN = "UNKNOWN"


@dataclass
class Command:
    """Normalized internal command structure.
    
    Compatible with both current rule-based parsing and future AI / voice parsers.
    """
    action: ActionType
    target: str = ""
    raw_input: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert command to a plain dictionary for serialization or logging."""
        return {
            "action": self.action.value,
            "target": self.target,
            "raw_input": self.raw_input,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Command":
        """Reconstruct command from dictionary representation (useful for AI parser JSON output)."""
        action_str = data.get("action", ActionType.UNKNOWN.value)
        try:
            action = ActionType(action_str)
        except ValueError:
            action = ActionType.UNKNOWN
        return cls(
            action=action,
            target=data.get("target", ""),
            raw_input=data.get("raw_input", ""),
            parameters=data.get("parameters", {}),
        )


@dataclass
class CommandResult:
    """Result of an executed command."""
    success: bool
    message: str
    action: ActionType
    target: str = ""
    pet_state: str = "idle"  # Desired pet animation state following execution (e.g. success, error, idle)
