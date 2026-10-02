"""Immutable interpretation data; these models never authorize OS actions."""
from dataclasses import dataclass
from enum import Enum


AUTO_EXECUTE_THRESHOLD = 0.85


class IntentType(str, Enum):
    OPEN_APPLICATION = 'OPEN_APPLICATION'
    OPEN_WEBSITE = 'OPEN_WEBSITE'
    WEB_SEARCH = 'WEB_SEARCH'
    PLAY_MEDIA = 'PLAY_MEDIA'
    SHOW_HELP = 'SHOW_HELP'
    MEMORY_STORE = 'MEMORY_STORE'
    MEMORY_QUERY = 'MEMORY_QUERY'
    MEMORY_FORGET = 'MEMORY_FORGET'
    UNKNOWN = 'UNKNOWN'


class MatchReason(str, Enum):
    EXACT_PHRASE = 'exact_phrase'
    VOICE_NORMALIZED = 'voice_normalized'
    SMART_MATCH = 'smart_match'
    NEGATED_COMMAND = 'negated_command'
    AMBIGUOUS_TARGET = 'ambiguous_target'
    AMBIGUOUS_COMMAND = 'ambiguous_command'
    UNSUPPORTED_TARGET = 'unsupported_target'
    UNKNOWN_INTENT = 'unknown_intent'
    DISABLED_COMMAND = 'disabled_command'
    UNAVAILABLE_COMMAND = 'unavailable_command'
    LOW_CONFIDENCE = 'low_confidence'
    INVALID_INPUT = 'invalid_input'


@dataclass(frozen=True)
class CommandIntent:
    intent: IntentType
    target: str | None = None
    value: str | None = None
    confidence: float = 1.0
    source: str = 'rule_based'
    memory_type: str | None = None


@dataclass(frozen=True)
class InterpretationResult:
    matched: bool = False
    intent: CommandIntent | None = None
    command_id: str | None = None
    reason: MatchReason = MatchReason.UNKNOWN_INTENT
    confidence: float = 0.0
    memory_id: str | None = None
