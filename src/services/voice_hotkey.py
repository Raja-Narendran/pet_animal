"""Windows Ctrl + Win hold listener. No typed text is collected or retained."""
import ctypes
from ctypes import wintypes
import sys
import threading
from PyQt6.QtCore import QThread, pyqtSignal


class ChordState:
    CONTROL = {0xA2, 0xA3}
    WINDOWS = {0x5B, 0x5C}

    def __init__(self, pressed=()):
        self.pressed = set(pressed)
        # Keys already held at installation must be released before activation.
        self.armed = not self.pressed
        self.active = False

    def update(self, key, down, injected=False):
        if injected:
            return None
        if down and key in self.pressed:
            return None
        if down:
            self.pressed.add(key)
        else:
            self.pressed.discard(key)
        chord = (bool(self.pressed & self.CONTROL) and bool(self.pressed & self.WINDOWS)
                 and not self.pressed - (self.CONTROL | self.WINDOWS))
        if self.active and not chord:
            self.active = False
            return 'released'
        if not self.pressed & (self.CONTROL | self.WINDOWS):
            self.armed = True
        if down and chord and self.armed:
            self.active = True
            self.armed = False
            return 'activated'
        return None


class VoiceHotkeyListener(QThread):
    activated = pyqtSignal()
    released = pyqtSignal()
    status_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._thread_id = None

    def stop(self):
        self._stop_event.set()
        if self._thread_id and sys.platform == 'win32':
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x12, 0, 0)
        self.wait()

    def run(self):
        if sys.platform != 'win32':
            self.status_changed.emit('Voice shortcut requires Windows.')
            return
        try:
            self._run_windows()
        except Exception:
            self.status_changed.emit('Voice shortcut could not start. Microphone button remains available.')
        finally:
            self._thread_id = None

    def _run_windows(self):
        user = ctypes.WinDLL('user32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        pointer_result = ctypes.c_ssize_t
        callback_type = ctypes.WINFUNCTYPE(pointer_result, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KeyboardData(ctypes.Structure):
            _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD),
                        ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                        ('dwExtraInfo', ctypes.c_size_t)]

        user.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HANDLE
        user.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = pointer_result
        user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user.UnhookWindowsHookEx.restype = wintypes.BOOL
        user.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user.DispatchMessageW.restype = pointer_result
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user.GetMessageW.restype = wintypes.BOOL
        user.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user.GetAsyncKeyState.restype = ctypes.c_short
        user.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        kernel.GetCurrentThreadId.restype = wintypes.DWORD
        msg = wintypes.MSG()
        # Create the message queue before publishing the ID used for shutdown.
        user.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._thread_id = kernel.GetCurrentThreadId()
        state = ChordState(key for key in range(8, 256) if user.GetAsyncKeyState(key) & 0x8000
                           and key not in (0x10, 0x11, 0x12))

        @callback_type
        def callback(code, message, address):
            if code >= 0 and not self._stop_event.is_set():
                data = ctypes.cast(address, ctypes.POINTER(KeyboardData)).contents
                if message in (0x100, 0x101, 0x104, 0x105):
                    event = state.update(data.vkCode, message in (0x100, 0x104), bool(data.flags & 0x10))
                    if event == 'activated':
                        # An unassigned menu-mask key prevents Win release opening Start.
                        # Pass physical events through so modifier state cannot get stuck.
                        user.keybd_event(0xE8, 0, 0, 0)
                        user.keybd_event(0xE8, 0, 2, 0)
                        self.activated.emit()
                    elif event == 'released':
                        self.released.emit()
            return user.CallNextHookEx(None, code, message, address)

        hook = None
        try:
            if self._stop_event.is_set():
                return
            hook = user.SetWindowsHookExW(13, callback, kernel.GetModuleHandleW(None), 0)
            if not hook:
                self.status_changed.emit('Voice shortcut could not start (Windows error %s). Microphone button remains available.' % ctypes.get_last_error())
                return
            self.status_changed.emit('Ctrl + Windows hold-to-talk is ready.')
            while not self._stop_event.is_set():
                result = user.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:
                    if result < 0:
                        self.status_changed.emit('Voice shortcut listener stopped unexpectedly. Disable and enable it to retry.')
                    break
                user.TranslateMessage(ctypes.byref(msg))
                user.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            self.status_changed.emit('Voice shortcut could not start. Microphone button remains available.')
        finally:
            if hook:
                user.UnhookWindowsHookEx(hook)
            self._thread_id = None
