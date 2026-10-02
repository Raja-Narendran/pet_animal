"""Public, headless models for explicit local memories and deterministic retrieval."""
from dataclasses import dataclass, field
from enum import Enum


class MemoryType(str, Enum):
    PROFILE = 'PROFILE'
    PREFERENCE = 'PREFERENCE'
    KNOWLEDGE = 'KNOWLEDGE'
    HABIT = 'HABIT'
    RELATIONSHIP = 'RELATIONSHIP'
    NOTE = 'NOTE'
    CONTEXT = 'CONTEXT'
    SYSTEM = 'SYSTEM'


class MemoryScope(str, Enum):
    GLOBAL = 'GLOBAL'
    PROFILE = 'PROFILE'
    PET_PROFILE = 'PET_PROFILE'
    SESSION = 'SESSION'
    TEMPORARY = 'TEMPORARY'


class MemoryLifetime(str, Enum):
    PERSISTENT = 'persistent'
    SESSION = 'session'
    TEMPORARY = 'temporary'


class MemorySource(str, Enum):
    USER_MANUAL = 'USER_MANUAL'
    COMMAND = 'COMMAND'
    SYSTEM = 'SYSTEM'
    HABIT_ENGINE = 'HABIT_ENGINE'
    IMPORT = 'IMPORT'
    MIGRATION = 'MIGRATION'
    FUTURE_AI = 'FUTURE_AI'


class MemoryConflictType(str, Enum):
    DUPLICATE = 'DUPLICATE'
    VALUE_CHANGE = 'VALUE_CHANGE'
    SCOPE_CONFLICT = 'SCOPE_CONFLICT'
    TYPE_CONFLICT = 'TYPE_CONFLICT'


class MemoryConflict(ValueError):
    """A masked conflict for a UI to confirm; never includes decrypted secrets."""
    def __init__(self, conflict_type, existing):
        self.conflict_type = MemoryConflictType(conflict_type)
        self.existing = existing
        super().__init__(f'Memory {self.conflict_type.value.lower().replace("_", " ")} requires confirmation.')


@dataclass(frozen=True)
class MemoryQuery:
    text: str = ''
    memory_type: MemoryType | str | None = None
    memory_scope: MemoryScope | str | None = None
    tags: tuple[str, ...] = ()
    limit: int = 20


@dataclass(frozen=True)
class MemoryMatch:
    memory_id: str
    key: str
    value: str
    score: float
    match_reason: str
    sensitive: bool = False
    confidence: float = 1.0
    memory: dict = field(default_factory=dict, compare=False, repr=False)


DEFAULT_IMPORTANCE = {
    MemoryType.PROFILE: 1.0, MemoryType.PREFERENCE: 0.8,
    MemoryType.KNOWLEDGE: 0.6, MemoryType.HABIT: 0.5,
    MemoryType.RELATIONSHIP: 0.6, MemoryType.NOTE: 0.7,
    MemoryType.CONTEXT: 0.2, MemoryType.SYSTEM: 0.4,
}
