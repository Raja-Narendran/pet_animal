"""Bounded, read-only Windows Recent Items metadata (no shortcut execution)."""
import ctypes
import os
import time
import uuid
from pathlib import Path


def _guid(value):
    return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)


def _method(pointer, slot, restype, *argtypes):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(table[slot])


def shortcut_target(path):
    """Load a link and GetPath only; never call Resolve or invoke the shortcut."""
    ole = ctypes.OleDLL('ole32')
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    clsid = _guid('00021401-0000-0000-c000-000000000046')
    iid = _guid('000214f9-0000-0000-c000-000000000046')
    persist_iid = _guid('0000010b-0000-0000-c000-000000000046')
    try:
        ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(link))
        if _method(link, 0, ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p)(link, ctypes.byref(persist_iid), ctypes.byref(persist)) < 0:
            return None
        if _method(persist, 5, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_uint)(persist, str(path), 0) < 0:
            return None
        buffer = ctypes.create_unicode_buffer(32768)
        status = _method(link, 3, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint)(link, buffer, len(buffer), None, 4)
        return os.path.expandvars(buffer.value) if status == 0 and buffer.value else None
    except OSError:
        return None
    finally:
        for pointer in (persist, link):
            if pointer:
                _method(pointer, 2, ctypes.c_ulong)(pointer)


class WindowsRecentItems:
    def read(self, cancel=None, max_entries=2000, max_seconds=2.0):
        if os.name != 'nt':
            return {}, ''
        ole = ctypes.OleDLL('ole32')
        initialized = False
        try:
            ole.CoInitializeEx(None, 2)
            initialized = True
            buffer = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 8, None, 0, buffer) != 0:
                raise OSError('Recent Items unavailable')
            start = time.monotonic()
            records = {}
            with os.scandir(buffer.value) as entries:
                for index, entry in enumerate(entries):
                    if (cancel and cancel.is_set()) or index >= max_entries or time.monotonic() - start >= max_seconds:
                        return records, 'Windows recent activity was only partially available.'
                    if not entry.name.lower().endswith('.lnk') or not entry.is_file(follow_symlinks=False):
                        continue
                    try:
                        target = shortcut_target(Path(entry.path))
                        if target:
                            stamp = entry.stat(follow_symlinks=False).st_mtime
                            records[target] = max(stamp, records.get(target, 0))
                    except (OSError, ValueError):
                        continue
            return records, ''
        except OSError:
            return {}, 'Windows recent activity is unavailable; using Pet activity and modification dates.'
        finally:
            if initialized:
                ole.CoUninitialize()
