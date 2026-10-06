"""Offline Unicode text insertion. No clipboard, shell, or text retention."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import re
import sys


def parse_dictation(phrase):
    """None means an ordinary command; empty string means missing dictation."""
    match = re.match(r'^\s*type(?=\s|,|$)\s*,?\s*', phrase, re.IGNORECASE)
    if not match:
        return None
    text = phrase[match.end():].strip()
    for words, symbol in (('question mark', '?'), ('exclamation mark', '!'),
                          ('comma', ','), ('full stop', '.')):
        text = re.sub(r'\b' + words.replace(' ', r'\s+') + r'\b', symbol, text, flags=re.IGNORECASE)
    text = re.sub(r' +([?!,.])', r'\1', text)
    for index, char in enumerate(text):
        if char.isalpha():
            text = text[:index] + char.upper() + text[index + 1:]
            break
    return text


@dataclass(frozen=True)
class TypingTarget:
    window: int
    focus: int
    process: int
    thread: int


class GUIThreadInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('hwndActive', wintypes.HWND), ('hwndFocus', wintypes.HWND),
                ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND),
                ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND),
                ('rcCaret', wintypes.RECT)]


class KeyboardInput(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


class MouseInput(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class HardwareInput(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]


class InputUnion(ctypes.Union):
    _fields_ = [('ki', KeyboardInput), ('mi', MouseInput), ('hi', HardwareInput)]


class Input(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', wintypes.DWORD), ('data', InputUnion)]


class WindowsTypingService:
    MODIFIERS = (0x11, 0x10, 0x12, 0x5B, 0x5C)

    def __init__(self, user=None):
        self.user = user
        if self.user is None and sys.platform == 'win32':
            self.user = ctypes.WinDLL('user32', use_last_error=True)
            signatures = {
                'GetForegroundWindow': ([], wintypes.HWND),
                'GetWindowThreadProcessId': ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
                'GetGUIThreadInfo': ([wintypes.DWORD, ctypes.POINTER(GUIThreadInfo)], wintypes.BOOL),
                'IsWindow': ([wintypes.HWND], wintypes.BOOL),
                'GetAsyncKeyState': ([ctypes.c_int], ctypes.c_short),
                'SendInput': ([wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int], wintypes.UINT),
            }
            for name, (args, result) in signatures.items():
                method = getattr(self.user, name)
                method.argtypes, method.restype = args, result

    def capture_target(self):
        if self.user is None:
            return None
        window = self.user.GetForegroundWindow()
        process = wintypes.DWORD()
        thread = self.user.GetWindowThreadProcessId(window, ctypes.byref(process))
        info = GUIThreadInfo(cbSize=ctypes.sizeof(GUIThreadInfo))
        if (not window or not thread or process.value == os.getpid() or
                not self.user.GetGUIThreadInfo(thread, ctypes.byref(info)) or not info.hwndFocus):
            return None
        return TypingTarget(window, info.hwndFocus, process.value, thread)

    def target_is_current(self, target):
        return bool(target and self.user and self.user.IsWindow(target.window)
                    and self.user.IsWindow(target.focus) and self.capture_target() == target)

    def modifiers_released(self):
        return bool(self.user and not any(self.user.GetAsyncKeyState(key) & 0x8000 for key in self.MODIFIERS))

    def insert_text(self, target, text):
        """Caller polls modifiers for at most two seconds without blocking the UI."""
        if not text or len(text) > 4096 or any(ord(char) < 32 or ord(char) == 127 for char in text):
            return False, 'Voice typing needs valid text of at most 4096 characters.'
        try:
            encoded = text.encode('utf-16-le')
        except UnicodeError:
            return False, 'Voice typing could not encode this text.'
        units = [int.from_bytes(encoded[i:i + 2], 'little') for i in range(0, len(encoded), 2)]
        events = (Input * (len(units) * 2))()
        for index, unit in enumerate(units):
            events[index * 2] = Input(type=1, data=InputUnion(ki=KeyboardInput(wScan=unit, dwFlags=4)))
            events[index * 2 + 1] = Input(type=1, data=InputUnion(ki=KeyboardInput(wScan=unit, dwFlags=6)))
        if not self.target_is_current(target):
            return False, 'Voice typing cancelled: the selected field changed.'
        if not self.modifiers_released():
            return False, 'Voice typing cancelled: release all modifier keys.'
        sent = self.user.SendInput(len(events), events, ctypes.sizeof(Input))
        if sent != len(events):
            return False, ('Only part of the text was inserted. Check the field before trying again.'
                           if sent else 'The selected application did not accept voice typing.')
        return True, 'Text inserted.'
