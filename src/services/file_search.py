"""Offline filename search: optional Everything IPC client and bounded disk traversal."""
import csv
import ctypes
import io
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from ..commands.interpreter.file_rules import valid_query


SKIP_DIRECTORIES = frozenset({'windows', 'program files', 'program files (x86)', 'programdata',
    'appdata', '$recycle.bin', 'system volume information', '.git', '.venv', 'venv',
    'node_modules', '__pycache__', '.pytest_cache'})


def is_local_path(path):
    """Reject UNC/device namespaces and remote drives before touching the path."""
    raw = str(path)
    if not raw or any(ord(c) < 32 for c in raw) or raw.startswith(('\\\\', '//')):
        return False
    value = Path(raw)
    if not value.is_absolute():
        return False
    if os.name == 'nt':
        if not re.fullmatch(r'[A-Za-z]:', value.drive) or ':' in raw[2:]:
            return False
        return ctypes.windll.kernel32.GetDriveTypeW(value.anchor) == 3  # DRIVE_FIXED
    return True


def local_path(path):
    if not is_local_path(path):
        raise ValueError('Choose an absolute path on a local disk.')
    value = Path(path)
    # Inspect ancestors from the disk root down, before resolving a link target.
    # This prevents a local-looking junction from touching a network share.
    for component in (*reversed(value.parents), value):
        details = component.lstat()
        if stat.S_ISLNK(details.st_mode) or getattr(details, 'st_file_attributes', 0) & (0x400 | 0x1000 | 0x40000 | 0x400000):
            raise ValueError('Links and offline placeholders are not searched or opened.')
    resolved = value.resolve(strict=True)
    if not is_local_path(resolved):
        raise ValueError('Network and device paths are not supported.')
    return resolved


@dataclass(frozen=True)
class FileSearchResult:
    path: str
    is_folder: bool
    modified: float
    project: str | None = None
    opened: float | None = None
    opened_source: str | None = None


@dataclass(frozen=True)
class FileSearchResponse:
    results: tuple[FileSearchResult, ...] = ()
    backend: str = 'local'
    partial: bool = False
    notice: str = ''


def salesforce_project(path):
    if any(part.casefold().startswith('salesforce') for part in path.parent.parts):
        return 'Salesforce'
    for parent in list(path.parents)[:5]:
        if (parent / 'sfdx-project.json').is_file():
            return 'Salesforce'
    return None


def result_for(path, query, folder=False, extension=None, roots=()):
    try:
        resolved = local_path(path)
        if roots and not any(resolved.is_relative_to(root) for root in roots):
            return None
        details = resolved.stat()
        is_folder = stat.S_ISDIR(details.st_mode)
        if is_folder != folder or not (is_folder or stat.S_ISREG(details.st_mode)):
            return None
        if query.casefold() not in resolved.name.casefold():
            return None
        if extension and resolved.suffix.casefold() != extension.casefold():
            return None
        # Avoid hydrating cloud placeholders or traversing reparse points.
        attributes = getattr(details, 'st_file_attributes', 0)
        if attributes & (0x400 | 0x1000 | 0x40000 | 0x400000):
            return None
        return FileSearchResult(str(resolved), is_folder, details.st_mtime,
                                salesforce_project(resolved) if not folder else None)
    except (OSError, ValueError, RuntimeError):
        return None


class EverythingUnavailable(Exception):
    pass


class EverythingSearchBackend:
    """Calls only the locally configured/detected es.exe, with fixed switches.

    ES queries the running Everything client over local IPC. User text is escaped
    as a regex literal; no Everything operators or subprocess switches are accepted.
    """
    def __init__(self, executable, timeout=4.0):
        self.executable = str(executable)
        self.timeout = timeout

    def search(self, query, folder=False, extension=None, roots=(), cancel=None, limit=200):
        if not valid_query(query):
            raise ValueError('Enter a file name, or a name followed by folder.')
        try:
            executable = local_path(self.executable)
            if executable.name.casefold() != 'es.exe' or not executable.is_file():
                raise EverythingUnavailable()
            # Override persisted ES settings; request only a full-path CSV column.
            args = [str(executable), '-csv', '-no-header', '-full-path-and-name',
                    '-no-name', '-no-path-column', '-no-extension', '-no-size',
                    '-no-date-created', '-no-date-modified', '-no-date-accessed',
                    '-no-attributes', '-no-file-list-file-name', '-no-run-count',
                    '-no-date-run', '-no-date-recently-changed', '-no-highlight',
                    '-no-case', '-no-match-path', '-no-whole-word', '-no-pause',
                    '-sort', 'date-modified-descending', '-n', str(limit + 1),
                    '-timeout', '1500', '/ad' if folder else '/a-d', '-regex', re.escape(query)]
            if roots:
                # Regex path constraints are composed from escaped, validated local roots.
                expression = '|'.join(re.escape(str(root).rstrip('\\/') + os.sep) for root in roots)
                if len(roots) == 1:
                    args.extend(['-path', str(roots[0])])
                if len(roots) > 1:
                    # Multiple scopes use one literal full-path regex, preserving basename semantics.
                    args[args.index('-no-match-path')] = '-match-path'
                    # ES preserves Windows argument quotes for Everything syntax.
                    # An ignored space in extended regex mode makes list2cmdline
                    # quote the complete expression, including the scope alternation.
                    args[args.index('-regex') + 1] = rf'(?x) ^(?:{expression})(?:.*[\\/])?[^\\/]*{re.escape(query)}[^\\/]*$'
            # ES CSV exports are UTF-8, independent of the system console codepage.
            # The export exists only for this request and is removed with the temp directory.
            with tempfile.TemporaryDirectory(prefix='petanimal-search-') as directory:
                export = Path(directory) / 'results.csv'
                args.extend(['-export-csv', str(export)])
                completed = subprocess.run(args, capture_output=True, timeout=self.timeout,
                    shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if completed.returncode != 0 or not export.is_file() or export.stat().st_size > 4 * 1024 * 1024:
                    raise EverythingUnavailable()
                if cancel and cancel.is_set():
                    return FileSearchResponse(backend='Everything', partial=True, notice='Search cancelled.')
                output = export.read_text(encoding='utf-8-sig')
            rows = list(csv.reader(io.StringIO(output)))
            results = []
            for row in rows:
                if len(row) != 1:
                    raise EverythingUnavailable()
                item = result_for(row[0], query, folder, extension, roots)
                if item:
                    results.append(item)
            results.sort(key=lambda item: (-item.modified, item.path.casefold()))
            return FileSearchResponse(tuple(results[:limit]), 'Everything', len(rows) > limit)
        except (OSError, ValueError, UnicodeError, csv.Error, subprocess.SubprocessError) as error:
            raise EverythingUnavailable() from error


class LocalSearchBackend:
    def __init__(self, max_entries=100_000, max_seconds=5.0):
        self.max_entries, self.max_seconds = max_entries, max_seconds

    def search(self, query, folder=False, extension=None, roots=(), cancel=None, limit=200):
        if not valid_query(query):
            raise ValueError('Enter a file name, or a name followed by folder.')
        deadline, visited, partial = time.monotonic() + self.max_seconds, 0, False
        found, seen, stack = {}, set(), list(reversed(roots))
        while stack:
            if time.monotonic() >= deadline or visited >= self.max_entries or (cancel and cancel.is_set()):
                partial = True
                break
            directory = stack.pop()
            key = str(directory).casefold()
            if key in seen:
                continue
            seen.add(key)
            root_item = result_for(directory, query, folder, extension, roots) if folder else None
            if root_item:
                found[root_item.path.casefold()] = root_item
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if time.monotonic() >= deadline or visited >= self.max_entries or (cancel and cancel.is_set()):
                            partial = True
                            stack.clear()
                            break
                        visited += 1
                        try:
                            attributes = getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0)
                            if entry.is_symlink() or attributes & (0x400 | 0x1000 | 0x40000 | 0x400000):
                                continue
                            is_folder = entry.is_dir(follow_symlinks=False)
                            if is_folder and entry.name.casefold() not in SKIP_DIRECTORIES:
                                stack.append(Path(entry.path))
                            if is_folder != folder or query.casefold() not in entry.name.casefold():
                                continue
                            item = result_for(entry.path, query, folder, extension, roots)
                            if item:
                                found[item.path.casefold()] = item
                        except OSError:
                            partial = True
            except OSError:
                partial = True
        results = sorted(found.values(), key=lambda item: (-item.modified, item.path.casefold()))
        return FileSearchResponse(tuple(results[:limit]), 'local', partial or len(results) > limit)


class FileSearchService:
    def __init__(self, roots=None, everything_executable=None, integration_dir=None, local_backend=None, recent_reader=None):
        self.roots = None if roots is None else tuple(Path(root) for root in roots)
        self.everything_executable = everything_executable
        self.integration_dir = integration_dir
        self.local = local_backend or LocalSearchBackend()
        from .recent_files import WindowsRecentItems
        self.recent_reader = recent_reader or WindowsRecentItems()

    def _everything_path(self):
        if self.everything_executable:
            return self.everything_executable
        candidates = []
        if self.integration_dir:
            candidates.append(Path(self.integration_dir) / 'es.exe')
        for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)'):
            if base := os.environ.get(key):
                candidates.append(Path(base) / 'Everything' / 'es.exe')
        if located := shutil.which('es.exe'):
            candidates.append(Path(located))
        return next((str(path) for path in candidates if is_local_path(path) and path.is_file()), None)

    @staticmethod
    def default_roots():
        home = Path.home()
        roots = [home / name for name in ('Documents', 'Desktop', 'Downloads', 'Projects')]
        roots.extend((Path.cwd(), home))
        if os.name == 'nt':
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            roots.extend(Path(f'{chr(65 + index)}:\\') for index in range(26)
                         if mask & (1 << index) and ctypes.windll.kernel32.GetDriveTypeW(f'{chr(65 + index)}:\\') == 3)
        available = []
        for root in roots:
            try:
                safe = local_path(root)
                if safe.is_dir():
                    available.append(safe)
            except (OSError, ValueError, RuntimeError):
                continue
        return tuple(dict.fromkeys(available))

    def search(self, intent, cancel=None):
        response = self._search_backend(intent, cancel)
        records, notice = self.recent_reader.read(cancel=cancel)
        response = replace(response, notice="\n".join(filter(None, (response.notice, notice))))
        return self.merge_activity(response, intent, records, 'Windows', cancel)

    def merge_activity(self, response, intent, records, source='Pet', cancel=None):
        filters = dict(intent.filters)
        roots = self.roots if self.roots is not None else (() if response.backend == 'Everything' else self.default_roots())
        if response.notice.startswith('Search folders are unavailable'):
            return response
        merged = {item.path.casefold(): item for item in response.results}
        for path, stamp in records.items():
            if cancel and cancel.is_set():
                break
            item = result_for(path, intent.query, filters.get('kind') == 'folder', filters.get('extension'), roots)
            if item:
                key = item.path.casefold()
                previous = merged.get(key, item)
                if not previous.opened or stamp > previous.opened:
                    merged[key] = replace(previous, opened=stamp, opened_source=source)
        items = sorted(merged.values(), key=lambda item: (item.opened is None, -(item.opened or 0), -item.modified, item.path.casefold()))
        return replace(response, results=tuple(items))

    def _search_backend(self, intent, cancel=None):
        if intent.intent.value != 'FILE_SEARCH' or intent.action not in ('FIND', 'FIND_AND_OPEN') or not valid_query(intent.query):
            raise ValueError('Enter a file name, or a name followed by folder.')
        filters = dict(intent.filters)
        if set(filters) - {'kind', 'extension'} or filters.get('kind', 'file') not in ('file', 'folder'):
            raise ValueError('Invalid file search filters.')
        requested = self.roots if self.roots is not None else self.default_roots()
        roots = []
        inaccessible = False
        for root in requested:
            try:
                root = local_path(root)
                if root.is_dir():
                    roots.append(root)
                else:
                    inaccessible = True
            except (OSError, ValueError):
                inaccessible = True
        options = dict(folder=filters.get('kind') == 'folder', extension=filters.get('extension'),
                       roots=tuple(roots), cancel=cancel)
        if self.roots is not None and not roots:
            return FileSearchResponse(partial=True, notice='Search folders are unavailable. Review Settings → Local file search.')
        if executable := self._everything_path():
            try:
                # An unconfigured Everything query covers its local index; configured roots restrict it.
                indexed_options = dict(options, roots=tuple(roots) if self.roots is not None else ())
                response = EverythingSearchBackend(executable).search(intent.query, **indexed_options)
                return response if not inaccessible else FileSearchResponse(response.results, response.backend, True)
            except EverythingUnavailable:
                notice = 'Everything is unavailable; searched local folders instead.'
        else:
            notice = ''
        response = self.local.search(intent.query, **options)
        return FileSearchResponse(response.results, response.backend, response.partial or inaccessible, notice)
