"""Windows user-bound encryption for sensitive memory values (no stored key)."""
import base64
import ctypes
import sys
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _transform(data: bytes, decrypt: bool) -> bytes:
    if sys.platform != 'win32':
        raise ValueError('Sensitive memories require Windows user encryption.')
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), 'Pet Animal memory', None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise ValueError('Windows could not unlock this memory for the current user.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def encrypt(value: str) -> str:
    return 'dpapi:' + base64.b64encode(_transform(value.encode('utf8'), False)).decode('ascii')


def decrypt(value: str) -> str:
    if not value.startswith('dpapi:'):
        raise ValueError('Invalid encrypted memory.')
    return _transform(base64.b64decode(value[6:], validate=True), True).decode('utf8')
