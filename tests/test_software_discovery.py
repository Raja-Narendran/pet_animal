"""Offline provider, validation and merging tests; no installed app is executed."""
from unittest.mock import MagicMock
import os
import pytest
from src.services.software_discovery import (DiscoveredApplication, DiscoverySource as Source,
    ValidationStatus as Status, ApplicationValidator, SoftwareDiscoveryService)
from src.services.software_discovery.start_menu import StartMenuDiscoveryProvider
from src.services.software_discovery.registry import RegistryDiscoveryProvider, icon_executable
from src.services.software_discovery.service import ApplicationDeduplicator, PathDiscoveryProvider


@pytest.fixture
def executable(tmp_path):
    path = tmp_path / 'Spotify.exe'
    path.write_bytes(b'MZ')
    return path


def candidate(path, name='Spotify', source=Source.START_MENU_USER, **kwargs):
    return DiscoveredApplication.candidate(name, str(path) if path else None, source, **kwargs)


@pytest.mark.parametrize('name', sorted(ApplicationValidator.DENIED | ApplicationValidator.HELPERS) + ['unins000.exe', 'uninstall.exe'])
def test_dangerous_executables_never_launchable(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b'MZ')
    result = ApplicationValidator().validate(candidate(path))
    assert not result.launchable
    assert result.validation_status in (Status.SYSTEM_COMPONENT, Status.UNINSTALLER)


@pytest.mark.parametrize('extension', ['.com', '.bat', '.cmd', '.ps1', '.vbs', '.js', '.dll', '.lnk'])
def test_scripts_and_non_exe_targets_rejected(tmp_path, extension):
    path = tmp_path / ('Spotify' + extension)
    path.touch()
    assert ApplicationValidator().validate(candidate(path)).validation_status == Status.UNSUPPORTED_TARGET


@pytest.mark.parametrize('path', ['relative.exe', 'C:\\app.exe:stream', '\\\\server\\app.exe', 'C:\\bad\napp.exe', 'https://example.com/app.exe', '"C:\\app.exe"', 'C:\\app.exe /c'])
def test_malformed_and_remote_paths_rejected(path):
    status, _ = ApplicationValidator.validate_path(path)
    assert status != Status.VALID


def test_valid_missing_directory_and_arguments(executable, tmp_path):
    result = ApplicationValidator().validate(candidate(executable))
    assert result.launchable and result.validation_status == Status.VALID
    assert ApplicationValidator().validate(candidate(executable, arguments='--url arbitrary')).validation_status == Status.REQUIRES_REVIEW
    executable.unlink()
    assert ApplicationValidator().validate(candidate(executable)).validation_status == Status.MISSING_EXECUTABLE
    directory = tmp_path / 'directory.exe'
    directory.mkdir()
    assert ApplicationValidator.validate_path(str(directory))[0] == Status.MISSING_EXECUTABLE


def test_start_menu_reads_shortcuts_only_and_continues(executable, tmp_path):
    root = tmp_path / 'Programs'
    root.mkdir()
    for name in ('Spotify.lnk', 'Broken.lnk', 'Uninstall.lnk', 'PowerShell.lnk', 'Ignore.txt'):
        (root / name).touch()
    def resolve(path):
        if path.stem == 'Broken':
            raise OSError('broken')
        target = executable if path.stem == 'Spotify' else tmp_path / ('unins000.exe' if path.stem == 'Uninstall' else 'powershell.exe')
        target.touch()
        return dict(target_path=str(target), arguments='', working_directory=str(tmp_path), icon_path=None)
    provider = StartMenuDiscoveryProvider([(root, Source.START_MENU_USER)], resolve)
    results = SoftwareDiscoveryService([provider]).discover()
    assert len(results) == 4
    by_name = {app.name: app for app in results}
    assert by_name['Spotify'].launchable
    assert by_name['Broken'].validation_status == Status.INVALID_PATH
    assert not by_name['Uninstall'].launchable and not by_name['PowerShell'].launchable


def test_same_path_merges_metadata(executable):
    items = [candidate(executable), candidate(executable, source=Source.REGISTRY_HKLM, publisher='Spotify AB', version='1.2')]
    results = SoftwareDiscoveryService([MagicMock(discover=lambda: iter(items))]).discover()
    assert len(results) == 1
    assert results[0].launchable and results[0].publisher == 'Spotify AB' and results[0].version == '1.2'
    assert results[0].sources == (Source.START_MENU_USER, Source.REGISTRY_HKLM)


def test_registry_metadata_only_merges_by_name_but_distinct_paths_survive(executable, tmp_path):
    validator = ApplicationValidator()
    items = [validator.validate(candidate(executable)), validator.validate(candidate(None, source=Source.REGISTRY_HKCU, publisher='Spotify AB'))]
    assert ApplicationDeduplicator().merge(items)[0].publisher == 'Spotify AB'
    other = tmp_path / 'another.exe'
    other.touch()
    assert len(ApplicationDeduplicator().merge([items[0], validator.validate(candidate(other))])) == 2


def test_provider_failure_does_not_stop_other_sources(executable):
    broken = MagicMock()
    broken.discover.side_effect = OSError('inaccessible')
    service = SoftwareDiscoveryService([broken, MagicMock(discover=lambda: iter([candidate(executable)]))])
    assert len(service.discover()) == 1 and service.errors
    assert not SoftwareDiscoveryService([broken]).discover(cancelled=lambda: True)


@pytest.mark.parametrize('value,expected', [('"C:\\Apps\\Spotify.exe",0', 'C:\\Apps\\Spotify.exe'), ('C:\\Apps\\Spotify.exe,-3', 'C:\\Apps\\Spotify.exe'), ('C:\\Apps\\Spotify.exe /uninstall', None), ('C:\\Apps\\icon.dll,1', None), (42, None)])
def test_registry_icon_parsing_never_treats_commands_as_paths(value, expected):
    assert icon_executable(value) == expected


class FakeKey:
    def __init__(self, name):
        self.name = name
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class FakeRegistry:
    HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE = 'user', 'machine'
    KEY_READ, KEY_WOW64_64KEY, KEY_WOW64_32KEY = 1, 2, 4
    def __init__(self, records):
        self.records, self.visited = records, []
    def OpenKey(self, root, name, reserved=0, access=0):
        if isinstance(root, str):
            self.visited.append((root, name, access))
            return FakeKey('root')
        if name == 'denied':
            raise PermissionError()
        return FakeKey(name)
    def EnumKey(self, root, index):
        try:
            return list(self.records)[index]
        except IndexError:
            raise OSError() from None
    def QueryValueEx(self, key, name):
        try:
            return self.records[key.name][name], 1
        except KeyError:
            raise OSError() from None


def test_registry_views_metadata_and_uninstall_safety(executable):
    registry = FakeRegistry({'denied': {}, 'spotify': {'DisplayName': 'Spotify', 'DisplayIcon': f'"{executable}",0', 'Publisher': 'Spotify AB', 'DisplayVersion': '1.2'},
        'metadata': {'DisplayName': 'Only metadata', 'UninstallString': str(executable)}, 'malformed': {'DisplayName': 123}})
    results = SoftwareDiscoveryService([RegistryDiscoveryProvider(registry)]).discover()
    assert len(registry.visited) == 3
    assert {access for _, _, access in registry.visited} == {1, 3, 5}
    assert len(results) == 2
    spotify = next(app for app in results if app.name == 'Spotify')
    assert spotify.launchable and spotify.publisher == 'Spotify AB' and len(spotify.sources) == 3
    assert not next(app for app in results if app.name == 'Only metadata').launchable


def test_path_uses_only_known_names(monkeypatch, executable):
    which = MagicMock(return_value=str(executable))
    monkeypatch.setattr('shutil.which', which)
    assert len(list(PathDiscoveryProvider().discover())) == len(PathDiscoveryProvider.NAMES)
    assert [call.args[0] for call in which.call_args_list] == list(PathDiscoveryProvider.NAMES)


def test_logging_reports_counts_without_local_paths(caplog, executable):
    caplog.set_level('INFO')
    service = SoftwareDiscoveryService([MagicMock(discover=lambda: iter([candidate(executable)]))])
    service.discover()
    assert '1 candidates' in caplog.text and str(executable) not in caplog.text


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows Shell link API')
def test_native_shell_link_round_trip_without_execution(executable, tmp_path):
    import ctypes
    import uuid
    from ctypes import wintypes
    from src.services.software_discovery.start_menu import read_shortcut
    class GUID(ctypes.Structure):
        _fields_ = [('data', ctypes.c_ubyte * 16)]
    def guid(value):
        return GUID((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))
    def method(pointer, index, *args):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *args)(table[index])
    ole = ctypes.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    initialized = ole.CoInitializeEx(None, 2)
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype = ctypes.c_long
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    path = tmp_path / 'Spotify.lnk'
    try:
        assert ole.CoCreateInstance(ctypes.byref(guid('00021401-0000-0000-C000-000000000046')), None, 1,
            ctypes.byref(guid('000214F9-0000-0000-C000-000000000046')), ctypes.byref(link)) >= 0
        assert method(link, 20, wintypes.LPCWSTR)(link, str(executable)) >= 0
        assert method(link, 9, wintypes.LPCWSTR)(link, str(tmp_path)) >= 0
        assert method(link, 11, wintypes.LPCWSTR)(link, '--review-only') >= 0
        assert method(link, 0, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(link,
            ctypes.byref(guid('0000010b-0000-0000-C000-000000000046')), ctypes.byref(persist)) >= 0
        assert method(persist, 6, wintypes.LPCWSTR, wintypes.BOOL)(persist, str(path), True) >= 0
        metadata = read_shortcut(path)
        assert metadata['target_path'] == str(executable) and metadata['arguments'] == '--review-only'
        assert metadata['working_directory'] == str(tmp_path)
        results = SoftwareDiscoveryService([StartMenuDiscoveryProvider([(tmp_path, Source.START_MENU_USER)])]).discover()
        assert len(results) == 1 and results[0].validation_status == Status.REQUIRES_REVIEW
    finally:
        for pointer in (persist, link):
            if pointer:
                method(pointer, 2)(pointer)
        if initialized >= 0:
            ole.CoUninitialize()
