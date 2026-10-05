"""Approved routines and a deterministic, Qt-free sequential engine.

Only the owner thread uses the service/database. The engine does not launch OS
processes or sleep: its caller dispatches a prepared step and supplies an outcome.
"""
import json
import math
import re
from pathlib import Path
from dataclasses import dataclass, replace
from ..services.windows_launcher import WindowsLauncher, BLOCKED_FILE_EXTENSIONS
from ..services.file_search import local_path
from ..services.software_discovery import ApplicationValidator, ValidationStatus

STEP_LABELS = {'application': 'Open App', 'url': 'Open URL', 'folder': 'Open Folder', 'file': 'Open File',
               'wait': 'Wait', 'message': 'Display Message'}


@dataclass(frozen=True)
class WorkflowStep:
    type: str
    value: str | float

    def to_dict(self):
        return {'type': self.type, 'value': self.value}


@dataclass(frozen=True)
class StepResult:
    position: int
    type: str
    status: str = 'pending'
    outcome: str = ''


@dataclass(frozen=True)
class RunResult:
    id: str
    routine_id: str
    name: str
    status: str
    steps: tuple[StepResult, ...]
    message: str = ''


class WorkflowService:
    def __init__(self, core):
        self.core = core
        self.active = None

    def ensure_idle(self, routine_id=None):
        if self.active is not None and (routine_id is None or self.active.result.routine_id == routine_id):
            raise ValueError('Stop the running routine before changing it or importing/restoring data.')

    def validate_steps(self, steps, *, live=False, connection=None):
        if not isinstance(steps, list) or not 1 <= len(steps) <= 50:
            raise ValueError('A routine needs 1â€“50 steps.')
        db = connection if connection is not None else self.core.db
        prepared = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or set(step) != {'type', 'value'}:
                raise ValueError(f'Step {index + 1}: invalid step settings.')
            kind, value = step['type'], step['value']
            if not isinstance(kind, str) or kind not in STEP_LABELS:
                raise ValueError(f'Step {index + 1}: unknown step type.')
            if kind == 'wait':
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 90:
                    raise ValueError(f'Step {index + 1}: wait must be 0â€“90 seconds.')
            else:
                if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                    raise ValueError(f'Step {index + 1}: enter a target without control characters.')
                value = value.strip()
                if kind == 'message' and len(value) > 100:
                    raise ValueError(f'Step {index + 1}: message must contain 1â€“100 characters.')
                if kind == 'url':
                    try:
                        self.core.validate_action('url', value)
                    except ValueError:
                        raise ValueError(f'Step {index + 1} (Open URL): enter a valid HTTPS address, such as https://example.com, without credentials, spaces or a non-standard port.') from None
                if kind == 'application':
                    if value not in WindowsLauncher.SUPPORTED_APPS:
                        if not re.fullmatch(r'app-[0-9a-f-]{36}', value):
                            raise ValueError(f'Step {index + 1}: choose an approved application.')
                        app = db.execute('SELECT * FROM registered_applications WHERE id=?', (value,)).fetchone()
                        if live and (not app or not app['enabled'] or app['needs_repair'] or
                                     ApplicationValidator.validate_registered_path(app['executable_path'])[0] != ValidationStatus.VALID):
                            raise ValueError(f'Step {index + 1}: application is unavailable. Choose or repair it.')
                    elif live and isinstance(self.core.launcher, WindowsLauncher):
                        # Preflight the two builtins that are not supplied with Windows.
                        if value == 'vscode' and not self.core.launcher.find_vscode():
                            raise ValueError(f'Step {index + 1}: VS Code could not be found.')
                        if value == 'chrome' and not self.core.launcher.find_chrome():
                            import shutil
                            if not shutil.which('chrome.exe'):
                                raise ValueError(f'Step {index + 1}: Chrome could not be found.')
                if kind in ('folder', 'file'):
                    from ..services.file_search import is_local_path
                    if not is_local_path(value):
                        raise ValueError(f'Step {index + 1}: choose an absolute {kind} on a local fixed disk.')
                    if kind == 'file' and Path(value).suffix.casefold() in BLOCKED_FILE_EXTENSIONS:
                        raise ValueError(f'Step {index + 1}: executable files, scripts and shortcuts must use approved application steps.')
                    if live:
                        try:
                            target = local_path(value)
                            if not (target.is_dir() if kind == 'folder' else target.is_file()):
                                raise ValueError()
                            value = str(target)
                        except (OSError, ValueError, RuntimeError):
                            raise ValueError(f'Step {index + 1}: {kind} is missing or unsafe.') from None
            prepared.append(WorkflowStep(kind, value))
        return tuple(prepared)

    def list(self):
        records = self.core.rows('SELECT r.id,r.command_id,r.steps,c.name,c.enabled FROM routines r JOIN commands c ON c.id=r.command_id ORDER BY c.name')
        for row in records:
            row['steps'] = json.loads(row['steps'])
            row['phrases'] = [p['phrase'] for p in self.core.rows('SELECT phrase FROM command_phrases WHERE command_id=? ORDER BY rowid', (row['command_id'],))]
            last = self.core.rows('SELECT status FROM workflow_runs WHERE routine_id=? ORDER BY started_at DESC LIMIT 1', (row['id'],))
            row['last_result'] = last[0]['status'] if last else 'Never run'
            row['issues'] = self.issues(row['steps'])
        return records

    def get(self, routine_id):
        return next((r for r in self.list() if r['id'] == routine_id), None)

    def issues(self, steps):
        try:
            self.validate_steps(steps, live=True)
            return ''
        except ValueError as error:
            return str(error)

    def _save(self, name, phrases, steps, enabled=True, routine_id=None, *, imported=False):
        from .application import identifier
        if routine_id is not None:
            self.ensure_idle(routine_id)
        prepared = self.validate_steps(steps, live=not imported)
        existing = self.core.rows('SELECT command_id FROM routines WHERE id=?', (routine_id,)) if routine_id else []
        if routine_id and not existing:
            raise ValueError('This routine no longer exists.')
        routine_id = routine_id or identifier()
        command_id = existing[0]['command_id'] if existing else identifier()
        # Insert after the command; action validation accepts only the private
        # creation token while this transaction establishes the linked routine.
        self.core._routine_creation = routine_id
        try:
            self.core._write_command(command_id, name, 'routine', routine_id, phrases, enabled)
            self.core.db.execute('INSERT INTO routines VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET steps=excluded.steps',
                (routine_id, command_id, json.dumps([s.to_dict() for s in prepared])))
        finally:
            self.core._routine_creation = None
        return routine_id

    def save(self, name, phrases, steps, enabled=True, routine_id=None):
        with self.core.db:
            result = self._save(name, phrases, steps, enabled, routine_id)
        self.core.changed()
        return result

    def delete(self, routine_id):
        self.ensure_idle(routine_id)
        record = self.get(routine_id)
        if record:
            self.core.delete_command(record['command_id'])

    def set_enabled(self, routine_id, enabled):
        self.ensure_idle(routine_id)
        record = self.get(routine_id)
        if record is None or type(enabled) is not bool:
            raise ValueError('Choose an existing routine and a valid enabled state.')
        if enabled:
            self.validate_steps(record['steps'], live=True)
        with self.core.db:
            self.core.db.execute('UPDATE commands SET enabled=? WHERE id=?', (int(enabled), record['command_id']))
        self.core.changed()

    def duplicate(self, routine_id):
        record = self.get(routine_id)
        if not record:
            raise ValueError('This routine no longer exists.')
        # A duplicate is a draft; phrases must be chosen to avoid collisions.
        return dict(name=record['name'] + ' copy', phrases=[], steps=record['steps'], enabled=False)

    def start(self, routine_id, phrase=None):
        from .application import identifier, now, normalize
        if self.active:
            raise ValueError('A routine is already running.')
        record = self.get(routine_id)
        if not record or not record['enabled']:
            raise ValueError('That routine is disabled or no longer available.')
        trigger = normalize(phrase if phrase is not None else record['phrases'][0])
        if trigger not in {normalize(p) for p in record['phrases']}:
            raise ValueError('Use an exact registered routine phrase.')
        engine = WorkflowEngine(identifier(), record)
        with self.core.db:
            self.core.db.execute('INSERT INTO workflow_runs VALUES (?,?,NULL,?,?,?,?)',
                (engine.result.id, routine_id, record['name'], 'running', now(), ''))
            for item in engine.result.steps:
                self.core.db.execute('INSERT INTO workflow_step_runs(run_id,position,step_type,status) VALUES (?,?,?,?)',
                    (engine.result.id, item.position, item.type, item.status))
        self.active = engine
        engine.command_id = record['command_id']
        engine.phrase = trigger
        # The same safe validation runs again before each dispatch.
        try:
            self.validate_steps(record['steps'], live=True)
        except ValueError as error:
            engine.fail_preflight(str(error))
            self.finish()
        return engine

    def persist_progress(self):
        from .application import now
        engine = self.active
        if not engine:
            return
        with self.core.db:
            for item in engine.result.steps:
                self.core.db.execute('UPDATE workflow_step_runs SET status=?,outcome=?,started_at=CASE WHEN started_at=? AND ?<>? THEN ? ELSE started_at END,finished_at=CASE WHEN ? IN (?,?,?,?) AND finished_at=? THEN ? ELSE finished_at END WHERE run_id=? AND position=?',
                    (item.status, item.outcome, '', item.status, 'pending', now(), item.status, 'success', 'failed', 'skipped', 'cancelled', '', now(), engine.result.id, item.position))

    def finish(self):
        from .application import identifier, now
        engine = self.active
        if not engine or engine.result.status == 'running':
            return
        self.persist_progress()
        with self.core.db:
            history_id = identifier()
            success = engine.result.status == 'success'
            reason = '' if success else ('Routine cancelled.' if engine.result.status == 'cancelled' else 'Routine failed; see workflow step outcomes.')
            self.core.db.execute('INSERT INTO command_history VALUES (?,?,?,?,?,?)',
                (history_id, engine.command_id, engine.phrase, 'success' if success else 'failed', reason, now()))
            self.core.db.execute('UPDATE workflow_runs SET status=?,finished_at=?,history_id=? WHERE id=?',
                (engine.result.status, now(), history_id, engine.result.id))
        self.active = None
        self.core.changed()

    def recover_interrupted(self):
        # An OS crash must not resume actions or leave a permanently running record.
        from .application import identifier, now
        with self.core.db:
            rows = self.core.rows("SELECT w.*,r.command_id FROM workflow_runs w LEFT JOIN routines r ON r.id=w.routine_id WHERE w.status='running'")
            for row in rows:
                history_id = identifier()
                self.core.db.execute('INSERT INTO command_history VALUES (?,?,?,?,?,?)',
                    (history_id, row['command_id'], '[interrupted routine]', 'failed', 'Routine interrupted.', now()))
                self.core.db.execute("UPDATE workflow_runs SET status='cancelled',finished_at=?,history_id=? WHERE id=?", (now(), history_id, row['id']))
                self.core.db.execute("UPDATE workflow_step_runs SET status=CASE status WHEN 'running' THEN 'cancelled' ELSE 'skipped' END,outcome='interrupted',finished_at=? WHERE run_id=? AND status IN ('pending','running')", (now(), row['id']))


class WorkflowEngine:
    def __init__(self, run_id, routine):
        self.steps = tuple(WorkflowStep(s['type'], s['value']) for s in routine['steps'])
        self.result = RunResult(run_id, routine['id'], routine['name'], 'running',
                                tuple(StepResult(i, s.type) for i, s in enumerate(self.steps)))
        self.position = 0
        self.final_message = ''

    def begin_step(self):
        if self.result.status != 'running':
            return None
        if self.position == len(self.steps):
            self.result = replace(self.result, status='success', message=self.final_message or self.result.name + ' ready.')
            return None
        items = list(self.result.steps)
        items[self.position] = replace(items[self.position], status='running')
        self.result = replace(self.result, steps=tuple(items))
        return self.steps[self.position]

    def complete_step(self, success, outcome=''):
        if self.result.status != 'running':
            return
        items = list(self.result.steps)
        items[self.position] = replace(items[self.position], status='success' if success else 'failed',
                                       outcome='accepted' if success else (outcome or 'launch_failed'))
        if success:
            if self.steps[self.position].type == 'message':
                self.final_message = str(self.steps[self.position].value)
            self.position += 1
            self.result = replace(self.result, steps=tuple(items))
        else:
            for index in range(self.position + 1, len(items)):
                items[index] = replace(items[index], status='skipped')
            self.result = replace(self.result, status='failed', steps=tuple(items),
                                  message=f'Step {self.position + 1} ({STEP_LABELS[self.steps[self.position].type]}) failed. Review its settings and try again.')

    def fail_preflight(self, message):
        match = re.search(r'Step (\d+)', message)
        self.position = int(match[1]) - 1 if match else 0
        self.complete_step(False, 'preflight_failed')
        items = tuple(replace(s, status='skipped') if s.status == 'pending' else s for s in self.result.steps)
        self.result = replace(self.result, steps=items, message=message)

    def cancel(self):
        if self.result.status != 'running':
            return
        items = tuple(replace(s, status='cancelled' if s.status == 'running' else 'skipped', outcome='cancelled')
                      if s.status in ('pending', 'running') else s for s in self.result.steps)
        self.result = replace(self.result, status='cancelled', steps=items, message='Routine cancelled.')
