"""Text insertion tests never send actual keyboard events."""
import ctypes
from unittest.mock import MagicMock
import pytest
from src.services.windows_typing import (WindowsTypingService, TypingTarget,
    GUIThreadInfo, parse_dictation, Input)


@pytest.mark.parametrize('phrase, expected', [
    ('type how are you question mark', 'How are you?'),
    ('TYPE, hello comma world exclamation mark', 'Hello, world!'),
    ('type tamil full stop', 'Tamil.'), ('type வணக்கம்', 'வணக்கம்'),
    ('type 😀 hello', '😀 Hello'), ('type', ''), ('type, ', ''),
    ('open notepad', None), ('typewriter hello', None),
    ('type Mixed CASE?', 'Mixed CASE?'),
])
def test_parse(phrase, expected):
    assert parse_dictation(phrase) == expected


@pytest.fixture
def service():
    user = MagicMock()
    user.GetForegroundWindow.return_value = 100
    user.IsWindow.return_value = True
    user.GetAsyncKeyState.return_value = 0
    def identity(window, pointer):
        pointer._obj.value = 999999
        return 10
    def focus(thread, pointer):
        pointer._obj.hwndFocus = 101
        return True
    user.GetWindowThreadProcessId.side_effect = identity
    user.GetGUIThreadInfo.side_effect = focus
    user.SendInput.side_effect = lambda count, events, size: count
    return WindowsTypingService(user)


def test_capture_and_unicode(service):
    target = service.capture_target()
    assert target == TypingTarget(100, 101, 999999, 10)
    assert service.insert_text(target, 'Hi தமிழ் 😀')[0]
    count, events, size = service.user.SendInput.call_args.args
    encoded = 'Hi தமிழ் 😀'.encode('utf-16-le')
    units = [int.from_bytes(encoded[i:i+2], 'little') for i in range(0, len(encoded), 2)]
    assert count == len(units) * 2
    assert size == ctypes.sizeof(Input)
    assert [events[i * 2].ki.wScan for i in range(len(units))] == units
    assert all(events[i].ki.dwFlags == (4 if i % 2 == 0 else 6) for i in range(count))
    assert all(events[i].ki.wVk == 0 for i in range(count))


@pytest.mark.parametrize('failure', ['window', 'focus', 'closed', 'process', 'modifier'])
def test_changed_target_never_sends(service, failure):
    target = service.capture_target()
    if failure == 'window':
        service.user.GetForegroundWindow.return_value = 102
    elif failure == 'focus':
        def changed(thread, pointer):
            pointer._obj.hwndFocus = 103
            return True
        service.user.GetGUIThreadInfo.side_effect = changed
    elif failure == 'closed':
        service.user.IsWindow.return_value = False
    elif failure == 'process':
        def changed(window, pointer):
            pointer._obj.value = 999998
            return 10
        service.user.GetWindowThreadProcessId.side_effect = changed
    else:
        service.user.GetAsyncKeyState.return_value = -32768
    assert not service.insert_text(target, 'Hello')[0]
    service.user.SendInput.assert_not_called()


@pytest.mark.parametrize('count', [0, 1])
def test_failed_and_partial_input_is_not_retried(service, count):
    service.user.SendInput.side_effect = None
    service.user.SendInput.return_value = count
    success, message = service.insert_text(service.capture_target(), 'Hi')
    assert not success
    assert ('part' in message) == bool(count)
    service.user.SendInput.assert_called_once()


@pytest.mark.parametrize('text', ['', 'a' * 4097, 'a\nb', '\t', '\x7f', '\ud800'])
def test_invalid_text_never_sends(service, text):
    assert not service.insert_text(service.capture_target(), text)[0]
    service.user.SendInput.assert_not_called()


def test_capture_unavailable_or_own_process(service, monkeypatch):
    monkeypatch.setattr('src.services.windows_typing.os.getpid', lambda: 999999)
    assert service.capture_target() is None
    service.user = None
    assert service.capture_target() is None
    assert not service.insert_text(None, 'Hi')[0]
