"""Shared validation for detection, explicit approval, restore and every launch."""
import os
import re
from dataclasses import replace
from pathlib import Path
from .models import ValidationStatus


class ApplicationValidator:
    DENIED = frozenset({
        'cmd.exe', 'powershell.exe', 'pwsh.exe', 'reg.exe', 'regedit.exe',
        'wscript.exe', 'cscript.exe', 'mshta.exe', 'rundll32.exe', 'wmic.exe',
        'schtasks.exe', 'net.exe', 'net1.exe', 'sc.exe', 'diskpart.exe',
        'bcdedit.exe', 'taskkill.exe', 'shutdown.exe', 'msiexec.exe',
        'installutil.exe', 'regsvr32.exe', 'msbuild.exe', 'certutil.exe',
        'bitsadmin.exe', 'forfiles.exe', 'bash.exe', 'wsl.exe',
    })
    HELPERS = frozenset({'setup.exe', 'installer.exe', 'update.exe', 'updater.exe',
                         'crashpad_handler.exe', 'helper.exe'})

    @classmethod
    def validate_path(cls, value):
        if not isinstance(value, str) or not value or len(value) > 32767 or any(ord(c) < 32 for c in value):
            return ValidationStatus.INVALID_PATH, None
        # Remote/device paths may initiate network access or bypass normal file semantics.
        if value.startswith(('\\\\', '//')) or any(c in value for c in '"<>|*?'):
            return ValidationStatus.INVALID_PATH, None
        if ':' in value[2:]:  # No NTFS alternate streams.
            return ValidationStatus.INVALID_PATH, None
        path = Path(value)
        if not path.is_absolute():
            return ValidationStatus.INVALID_PATH, None
        try:
            resolved = path.resolve()
            if str(resolved).startswith(('\\\\', '//')):
                return ValidationStatus.INVALID_PATH, None
            for item in (path, resolved):
                name = item.name.casefold()
                if name in cls.DENIED:
                    return ValidationStatus.SYSTEM_COMPONENT, str(resolved)
                if name in cls.HELPERS or re.match(r'(?:uninstall|unins).*\.exe$', name):
                    return ValidationStatus.UNINSTALLER, str(resolved)
                if item.suffix.casefold() != '.exe':
                    return ValidationStatus.UNSUPPORTED_TARGET, str(resolved)
            if not resolved.is_file():
                return ValidationStatus.MISSING_EXECUTABLE, str(resolved)
            return ValidationStatus.VALID, str(resolved)
        except (OSError, ValueError, RuntimeError):
            return ValidationStatus.INVALID_PATH, None

    def validate(self, candidate):
        status, path = self.validate_path(candidate.executable_path)
        if candidate.executable_path is None:
            status = ValidationStatus.REQUIRES_REVIEW
        if re.search(r'\b(?:uninstall|uninstaller|setup|installer|updater)\b', candidate.normalized_name):
            status = ValidationStatus.UNINSTALLER
        # V1 launches only the approved executable, never shortcut arguments or cwd.
        if status == ValidationStatus.VALID and candidate.arguments.strip():
            status = ValidationStatus.REQUIRES_REVIEW
        return replace(candidate, executable_path=path, launchable=status == ValidationStatus.VALID,
                       validation_status=status)

    @classmethod
    def validate_registered_path(cls, value):
        status, path = cls.validate_path(value)
        if status in (ValidationStatus.VALID, ValidationStatus.MISSING_EXECUTABLE) and path:
            # Approval stores the resolved path. A later link/junction must not retarget it.
            if os.path.normcase(os.path.abspath(value)) != os.path.normcase(os.path.abspath(path)):
                return ValidationStatus.INVALID_PATH, None
        return status, path


def canonical_path(value):
    return os.path.normcase(str(Path(value).resolve())).casefold() if value else None
