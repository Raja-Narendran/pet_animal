"""Read Start Menu links with IShellLinkW/IPersistFile; never execute or Resolve links."""
import ctypes
import os
import uuid
from pathlib import Path
from .models import DiscoveredApplication, DiscoverySource, ValidationStatus


def read_shortcut(path):
    if os.name != 'nt':
        raise OSError('Shell links require Windows.')
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [('data', ctypes.c_ubyte * 16)]

    def guid(value):
        return GUID((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))

    def method(pointer, index, result, *args):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *args)(table[index])

    def checked(result):
        if result < 0:
            raise OSError('Could not read Shell link.')

    ole = ctypes.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype = ctypes.c_long
    initialized = ole.CoInitializeEx(None, 2)
    if initialized < 0 and initialized != -2147417850:  # Existing apartment is usable.
        checked(initialized)
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        checked(ole.CoCreateInstance(ctypes.byref(guid('00021401-0000-0000-C000-000000000046')),
                                    None, 1, ctypes.byref(guid('000214F9-0000-0000-C000-000000000046')),
                                    ctypes.byref(link)))
        checked(method(link, 0, ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
            link, ctypes.byref(guid('0000010b-0000-0000-C000-000000000046')), ctypes.byref(persist)))
        checked(method(persist, 5, ctypes.c_long, wintypes.LPCWSTR, wintypes.DWORD)(persist, str(path), 0))
        target = ctypes.create_unicode_buffer(32768)
        checked(method(link, 3, ctypes.c_long, wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p,
                       wintypes.DWORD)(link, target, len(target), None, 4))  # SLGP_RAWPATH
        metadata = {'target_path': os.path.expandvars(target.value)}
        for key, index in [('working_directory', 8), ('arguments', 10)]:
            buffer = ctypes.create_unicode_buffer(32768)
            checked(method(link, index, ctypes.c_long, wintypes.LPWSTR, ctypes.c_int)(link, buffer, len(buffer)))
            metadata[key] = buffer.value
        icon = ctypes.create_unicode_buffer(32768)
        icon_index = ctypes.c_int()
        result = method(link, 16, ctypes.c_long, wintypes.LPWSTR, ctypes.c_int, ctypes.POINTER(ctypes.c_int))(
            link, icon, len(icon), ctypes.byref(icon_index))
        metadata['icon_path'] = icon.value or None if result >= 0 else None
        return metadata
    finally:
        for pointer in (persist, link):
            if pointer:
                method(pointer, 2, ctypes.c_ulong)(pointer)
        if initialized >= 0:
            ole.CoUninitialize()


class StartMenuDiscoveryProvider:
    def __init__(self, roots=None, resolver=read_shortcut):
        self.resolver = resolver
        self.roots = roots if roots is not None else [
            (Path(os.environ[key]) / 'Microsoft/Windows/Start Menu/Programs', source)
            for key, source in [('APPDATA', DiscoverySource.START_MENU_USER),
                                ('PROGRAMDATA', DiscoverySource.START_MENU_SYSTEM)] if os.environ.get(key)]

    def discover(self):
        for root, source in self.roots:
            if str(root).startswith(('\\\\', '//')):
                continue
            for folder, directories, files in os.walk(root, followlinks=False):
                directories[:] = [name for name in directories
                                  if not Path(folder, name).is_symlink()
                                  and not getattr(os.path, 'isjunction', lambda path: False)(Path(folder, name))]
                for name in files:
                    path = Path(folder, name)
                    if path.suffix.casefold() != '.lnk' or path.is_symlink():
                        continue
                    try:
                        metadata = self.resolver(path)
                        yield DiscoveredApplication.candidate(path.stem, metadata.pop('target_path'), source,
                                                              shortcut_path=str(path), **metadata)
                    except (OSError, ValueError, KeyError, TypeError):
                        yield DiscoveredApplication.candidate(path.stem, None, source, shortcut_path=str(path),
                                                              validation_status=ValidationStatus.INVALID_PATH)
