"""Uninstall metadata only; uninstall commands are never launch targets."""
import os
import re
from .models import DiscoveredApplication, DiscoverySource


def icon_executable(value):
    if not isinstance(value, str):
        return None
    value = os.path.expandvars(value.strip())
    match = re.fullmatch(r'"([^"\r\n]+)"(?:\s*,\s*-?\d+)?|([^"\r\n]+?)(?:\s*,\s*-?\d+)?', value)
    if not match:
        return None
    target = (match[1] or match[2]).strip()
    return target if target.casefold().endswith('.exe') else None


class RegistryDiscoveryProvider:
    def __init__(self, registry=None):
        if registry is None and os.name == 'nt':
            import winreg
            registry = winreg
        self.registry = registry

    def discover(self):
        reg = self.registry
        if reg is None:
            return
        base = r'Software\Microsoft\Windows\CurrentVersion\Uninstall'
        locations = [(reg.HKEY_CURRENT_USER, base, DiscoverySource.REGISTRY_HKCU, 0),
                     (reg.HKEY_LOCAL_MACHINE, base, DiscoverySource.REGISTRY_HKLM, reg.KEY_WOW64_64KEY),
                     (reg.HKEY_LOCAL_MACHINE, base, DiscoverySource.REGISTRY_WOW6432, reg.KEY_WOW64_32KEY)]
        for hive, location, source, view in locations:
            try:
                with reg.OpenKey(hive, location, 0, reg.KEY_READ | view) as root:
                    index = 0
                    while True:
                        try:
                            child = reg.EnumKey(root, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            with reg.OpenKey(root, child) as key:
                                def read(name):
                                    try:
                                        value = reg.QueryValueEx(key, name)[0]
                                        return value if isinstance(value, str) else None
                                    except OSError:
                                        return None
                                name = read('DisplayName')
                                if not name or not name.strip():
                                    continue
                                icon = read('DisplayIcon')
                                # InstallLocation and UninstallString never imply a launch path.
                                yield DiscoveredApplication.candidate(name, icon_executable(icon), source,
                                    publisher=read('Publisher'), version=read('DisplayVersion'), icon_path=icon)
                        except (OSError, ValueError, TypeError):
                            continue
            except OSError:
                continue
