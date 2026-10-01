"""Immutable detection and trusted-registration records."""
from dataclasses import dataclass
from enum import Enum
import hashlib
import unicodedata


class DiscoverySource(str, Enum):
    START_MENU_USER = 'START_MENU_USER'
    START_MENU_SYSTEM = 'START_MENU_SYSTEM'
    REGISTRY_HKCU = 'REGISTRY_HKCU'
    REGISTRY_HKLM = 'REGISTRY_HKLM'
    REGISTRY_WOW6432 = 'REGISTRY_WOW6432'
    PATH = 'PATH'


class ValidationStatus(str, Enum):
    VALID = 'VALID'
    MISSING_EXECUTABLE = 'MISSING_EXECUTABLE'
    UNSUPPORTED_TARGET = 'UNSUPPORTED_TARGET'
    SYSTEM_COMPONENT = 'SYSTEM_COMPONENT'
    UNINSTALLER = 'UNINSTALLER'
    DUPLICATE = 'DUPLICATE'
    INVALID_PATH = 'INVALID_PATH'
    REQUIRES_REVIEW = 'REQUIRES_REVIEW'


def normalized_name(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


@dataclass(frozen=True)
class DiscoveredApplication:
    discovery_id: str
    name: str
    normalized_name: str
    executable_path: str | None
    source: DiscoverySource
    shortcut_path: str | None = None
    publisher: str | None = None
    version: str | None = None
    icon_path: str | None = None
    arguments: str = ''
    working_directory: str = ''
    launchable: bool = False
    validation_status: ValidationStatus = ValidationStatus.REQUIRES_REVIEW
    sources: tuple[DiscoverySource, ...] = ()

    @classmethod
    def candidate(cls, name, executable_path, source, **metadata):
        name = name.strip()
        identity = f'{source.value}|{normalized_name(name)}|{executable_path or ""}'
        key = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
        return cls(key, name, normalized_name(name), executable_path, source,
                   sources=(source,), **metadata)


@dataclass(frozen=True)
class RegisteredApplication:
    id: str
    name: str
    normalized_name: str
    executable_path: str
    publisher: str | None
    version: str | None
    icon_path: str | None
    source: str
    enabled: bool
    needs_repair: bool
    created_at: str
    updated_at: str
    aliases: tuple[str, ...] = ()
