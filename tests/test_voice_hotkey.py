"""Chord transitions and Windows listener lifecycle, without recording audio."""
import sys
from unittest.mock import MagicMock
import pytest
from src.services.voice_hotkey import ChordState, VoiceHotkeyListener


@pytest.mark.parametrize('ctrl', [0xA2, 0xA3])
@pytest.mark.parametrize('win', [0x5B, 0x5C])
@pytest.mark.parametrize('reverse', [False, True])
def test_chord_order_and_release(ctrl, win, reverse):
    first, second = (win, ctrl) if reverse else (ctrl, win)
    state = ChordState()
    assert state.update(first, True) is None
    assert state.update(second, True) == 'activated'
    assert state.update(second, True) is None
    assert state.update(first, False) == 'released'
    assert state.update(first, True) is None  # Must release both before retry.
    state.update(first, False)
    state.update(second, False)
    state.update(first, True)
    assert state.update(second, True) == 'activated'


def test_extra_keys_injected_and_initially_held_keys():
    state = ChordState()
    state.update(0x41, True)
    state.update(0xA2, True)
    assert state.update(0x5B, True) is None
    assert state.update(0x41, False) is None
    state.update(0xA2, False)
    state.update(0x5B, False)
    assert state.update(0xA2, True, injected=True) is None
    assert not state.pressed
    state = ChordState([0xA2])
    assert state.update(0x5B, True) is None
    state.update(0xA2, False)
    state.update(0x5B, False)
    state.update(0x5B, True)
    assert state.update(0xA2, True) == 'activated'
    assert state.update(0x41, True) == 'released'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows API')
def test_listener_install_failure(qtbot, monkeypatch):
    user, kernel = MagicMock(), MagicMock()
    user.GetAsyncKeyState.return_value = 0
    user.SetWindowsHookExW.return_value = 0
    monkeypatch.setattr('src.services.voice_hotkey.ctypes.WinDLL', lambda name, **kwargs: user if name == 'user32' else kernel)
    listener = VoiceHotkeyListener()
    messages = []
    listener.status_changed.connect(messages.append)
    listener.run()
    assert 'could not start' in messages[0]
    user.UnhookWindowsHookEx.assert_not_called()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows API')
def test_real_listener_install_and_stop(qtbot):
    listener = VoiceHotkeyListener()
    try:
        with qtbot.waitSignal(listener.status_changed, timeout=5000) as signal:
            listener.start()
        assert 'ready' in signal.args[0]
    finally:
        listener.stop()
    assert not listener.isRunning()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows callback ABI')
def test_native_callback_passes_keys_masks_start_and_unhooks(qtbot, monkeypatch):
    import ctypes
    from ctypes import wintypes
    from unittest.mock import call
    class Data(ctypes.Structure):
        _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD),
                    ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                    ('dwExtraInfo', ctypes.c_size_t)]
    user, kernel = MagicMock(), MagicMock()
    user.GetAsyncKeyState.return_value = 0
    user.SetWindowsHookExW.return_value = 1
    user.CallNextHookEx.return_value = 0
    monkeypatch.setattr('src.services.voice_hotkey.ctypes.WinDLL', lambda name, **kwargs: user if name == 'user32' else kernel)
    listener = VoiceHotkeyListener()
    events = []
    listener.activated.connect(lambda: events.append('down'))
    listener.released.connect(lambda: events.append('up'))
    def messages(*args):
        callback = user.SetWindowsHookExW.call_args.args[1]
        # Negative hook codes must pass through without dereferencing lParam.
        assert callback(-1, 0x100, 0) == 0
        for key, message, flags in [(0xA2, 0x100, 0x10), (0xA2, 0x100, 0),
                                    (0x5B, 0x100, 0), (0x5B, 0x100, 0),
                                    (0x5B, 0x101, 0), (0xA2, 0x101, 0)]:
            data = Data(vkCode=key, flags=flags)
            assert callback(0, message, ctypes.addressof(data)) == 0
        return 0
    user.GetMessageW.side_effect = messages
    listener.run()
    assert events == ['down', 'up']
    assert user.keybd_event.call_args_list == [call(0xE8, 0, 0, 0), call(0xE8, 0, 2, 0)]
    assert user.CallNextHookEx.call_count == 7
    user.UnhookWindowsHookEx.assert_called_once_with(1)
