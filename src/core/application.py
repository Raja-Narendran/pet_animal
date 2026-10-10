"""Single application core shared by both windows; no UI or HTTP dependency."""
import json
import re
import sqlite3
import uuid
import time
from dataclasses import asdict, replace
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from . import secrets
from .memory import MemoryService
from .memory.conversation import MemoryConversation, matching_memories, memory_kind
from .memory.service import normalize as normalize_memory
from .shortcuts import APPLICATION_NAMES, ApplicationShortcut, match_shortcuts
from .file_search import FileSearchSession
from .workflows import WorkflowService
from ..services.file_search import FileSearchService, FileSearchResponse, local_path
from ..config.settings import settings
from ..services.windows_launcher import WindowsLauncher
from ..services.software_discovery import DiscoveredApplication, RegisteredApplication, ApplicationValidator, ValidationStatus, DiscoverySource
from ..services.software_discovery.validator import canonical_path
from ..commands.interpreter.patterns import APPLICATION_ALIASES, WEBSITE_ALIASES
from ..commands.interpreter import (AUTO_EXECUTE_THRESHOLD, CommandIntent, InterpretationResult, IntentType, MatchReason,
                                    RuleBasedIntentInterpreter, IntentResolver, MemoryResolver)
from ..commands.interpreter.normalizer import normalize_input
from ..commands.interpreter.file_rules import file_intent, valid_query
from ..commands.interpreter.browser_rules import browser_fallback, website_url, DIRECT_WEBSITE_SOURCE
from ..commands.voice_phrases import normalize_mixed_voice
from ..utils.logger import get_logger

logger = get_logger('application')


def identifier():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize(text):
    return normalize_memory(text)


def text(value, label, limit=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise ValueError(f'{label} must contain 1–{limit} characters.')
    return value.strip()


DEFAULT_PET = dict(size=240, x=None, y=None, always_on_top=True, animations=True,
                   chat_width=320, text_size=13, background='#18181b', radius=20, opacity=0.94)
DEFAULT_APP = dict(launch_pet=True, start_minimized=False, tray=True, notifications=True, theme='light', page='Dashboard', voice_mode='google', google_voice_language='en-IN', voice_hotkey_enabled=False, default_music_player='youtube', spotify_open_mode='auto')


class ApplicationCore:
    def __init__(self, data_dir, launcher=None, file_search=None):
        self.root = Path(data_dir)
        for folder in ('database', 'pets/imported', 'backups', 'logs'):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'database/petanimal.db'
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA trusted_schema=OFF')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.launcher = launcher if launcher is not None else WindowsLauncher()
        self.interpreter = RuleBasedIntentInterpreter(memory_preferences=True)
        self.intent_resolver = IntentResolver()
        self.listeners = []
        self._memory_confirmations = {}
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 7:
            raise ValueError('This database requires a newer Pet Animal version.')
        if version == 0:
            migration = settings.BASE_DIR / 'src/database/migrations/001_initial.sql'
            self.db.executescript('BEGIN;\n' + migration.read_text(encoding='utf-8-sig') + '\nCOMMIT;')
        if version < 2:
            migration = settings.BASE_DIR / 'src/database/migrations/002_registered_applications.sql'
            self.db.executescript('BEGIN;\n' + migration.read_text(encoding='utf-8-sig') + '\nCOMMIT;')
        if version < 3:
            migration = settings.BASE_DIR / 'src/database/migrations/003_personal_memory_engine.sql'
            try:
                self.db.executescript('BEGIN;\n' + migration.read_text(encoding='utf-8-sig') + '\nCOMMIT;')
            except Exception:
                self.db.rollback()
                self.db.close()
                raise
        if version < 4:
            migration = settings.BASE_DIR / 'src/database/migrations/004_simplify_memory.sql'
            try:
                self.db.executescript('BEGIN;\n' + migration.read_text(encoding='utf-8-sig') + '\nCOMMIT;')
            except Exception:
                self.db.rollback()
                self.db.close()
        if version < 5:
            migration = settings.BASE_DIR / 'src/database/migrations/005_remove_activity_patterns.sql'
            try:
                self.db.executescript('BEGIN;\n' + migration.read_text(encoding='utf-8-sig') + '\nCOMMIT;')
            except Exception:
                self.db.rollback()
                self.db.close()
                raise
        if version < 6:
            migration = settings.BASE_DIR / "src/database/migrations/006_file_open_history.sql"
            self.db.executescript("BEGIN;\n" + migration.read_text(encoding="utf-8-sig") + "\nCOMMIT;")
        if version < 7:
            migration = settings.BASE_DIR / "src/database/migrations/007_workflows.sql"
            self.db.executescript("BEGIN;\n" + migration.read_text(encoding="utf-8-sig") + "\nCOMMIT;")
        self.workflows = WorkflowService(self)
        self._routine_creation = None
        self._seed()
        self.memory_service = MemoryService(self.db, changed=self.changed)
        self.memory_retriever = self.memory_service.retriever
        self.memory_conversation = MemoryConversation(self.memory_service)
        self.memory_resolver = MemoryResolver(self.memory_retriever)
        if isinstance(self.launcher, WindowsLauncher):
            self.launcher.registered_application_lookup = self.get_registered_application
        self.workflows.recover_interrupted()
        self._refresh_application_aliases()
        self.file_session = FileSearchSession(record_open=self._record_file_open)
        self.file_search = file_search if file_search is not None else self.create_file_search_service()

    def close(self):
        if self.workflows.active:
            self.workflows.active.cancel()
            self.workflows.finish()
        self.file_session.clear()
        self.memory_conversation.clear()
        self.memory_service.close_session()
        self.db.close()

    def changed(self):
        self._refresh_application_aliases()
        for callback in tuple(self.listeners):
            callback()

    def rows(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args)]

    def _seed(self):
        with self.db:
            for name, sensitive in [('Personal Information', 0), ('Password', 1), ('Credit and Debit card details', 1), ('Important Notes', 0)]:
                self.db.execute('INSERT OR IGNORE INTO memory_categories VALUES (?,?,?)', (identifier(), name, sensitive))
            for state, filename in settings.PET_STATES.items():
                self.db.execute('INSERT OR IGNORE INTO pet_assets VALUES (?,?,?,0)', ('builtin-' + state, 'Husky · ' + state.title(), filename))
            if not self.rows('SELECT id FROM pet_profiles'):
                self._write_profile(identifier(), 'Husky', 'builtin-idle', DEFAULT_PET, True)
            if not self.rows('SELECT id FROM commands') and not self.get_setting('commands_seeded', False):
                for key in sorted(WindowsLauncher.SUPPORTED_APPS):
                    self._write_command(identifier(), 'Open ' + key.title(), 'application', key, ['open ' + key, 'launch ' + key, 'start ' + key, key], True, True)
                for key, url in settings.SUPPORTED_URLS.items():
                    if key == 'spotify':
                        continue  # Added separately without taking application phrases.
                    self._write_command(identifier(), 'Open ' + key.title(), 'url', url, ['open ' + key, key], True, True)
                self.db.execute('INSERT INTO app_settings VALUES (?,?)', ('commands_seeded', 'true'))
            self._seed_spotify()

    def _seed_spotify(self):
        # One-time addition preserves later user deletion/disablement.
        if not self.get_setting('spotify_seeded', False):
            url = settings.SUPPORTED_URLS['spotify']
            if not any(c['action_type'] == 'url' and c['target'] == url for c in self.commands()):
                registered = {p['phrase'] for p in self.rows('SELECT phrase FROM command_phrases')}
                phrases = [p for p in ('open spotify website', 'spotify website') if p not in registered]
                if not phrases:
                    phrase = 'open spotify website'
                    index = 2
                    while phrase in registered:
                        phrase = f'open spotify website {index}'
                        index += 1
                    phrases = [phrase]
                self._write_command(identifier(), 'Open Spotify', 'url', url, phrases, True, True)
            self.db.execute('INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                            ('spotify_seeded', 'true'))

    def categories(self):
        return self.rows('SELECT * FROM memory_categories ORDER BY sensitive, name')

    def add_category(self, name, sensitive=False):
        with self.db:
            self.db.execute('INSERT INTO memory_categories VALUES (?,?,?)', (identifier(), text(name, 'Category', 100), int(bool(sensitive))))
        self.changed()

    def _category(self, category_id):
        found = self.rows('SELECT * FROM memory_categories WHERE id=?', (category_id,))
        if not found:
            raise ValueError('Choose an existing category.')
        return found[0]

    def memories(self, query='', category_id=None, **filters):
        return self.memory_service.list_memories(query, category_id, **filters)

    def get_memory(self, memory_id, reveal=False):
        return self.memory_service.get_memory(memory_id, reveal=reveal)

    def get_memory_by_key(self, key, consume=True, reveal=False):
        return self.memory_service.get_memory_by_key(key, consume=consume, reveal=reveal)

    def save_memory(self, category_id, title, key, value, description='', enabled=True, memory_id=None, **metadata):
        if key is None:
            slug = re.sub(r'[^a-z0-9_.]+', '.', title.strip().lower()).strip('.')
            key = slug if slug else 'custom.' + identifier()
        # An explicit ID edit is the established Manager's confirmed user action.
        if memory_id is None and self.rows('SELECT id FROM memories WHERE memory_key=?', (key,)):
            raise sqlite3.IntegrityError('Memory key already exists.')
        return self.memory_service.save_memory(category_id, title, key, value, description,
                                               enabled, memory_id, confirmed=bool(memory_id), **metadata)

    def delete_memory(self, memory_id):
        self.memory_service.delete_memory(memory_id)

    def export_memories(self):
        return self.memory_service.export_memories()

    def import_memories(self, payload):
        return self.memory_service.import_memories(payload, strict=True)

    @staticmethod
    def validate_action(action, target):
        if action == 'application' and target in WindowsLauncher.SUPPORTED_APPS:
            return
        if action == 'url' and isinstance(target, str) and len(target) <= 2048:
            parsed = urlparse(target)
            try:
                valid = parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and parsed.port in (None, 443) and not any(c.isspace() or ord(c) < 32 for c in target)
            except ValueError:
                valid = False
            if valid:
                return
        raise ValueError('Choose an allowlisted application or a valid HTTPS URL (no credentials).')

    def commands(self):
        records = self.rows('SELECT * FROM commands ORDER BY name')
        for row in records:
            row['target'] = json.loads(row['action_config'])['target']
            row['phrases'] = [p['phrase'] for p in self.rows('SELECT phrase FROM command_phrases WHERE command_id=? ORDER BY rowid', (row['id'],))]
        return records

    def application_shortcuts(self, query=''):
        """List enabled application commands without launching or recording activity."""
        applications = {app.id: app for app in self.list_registered_applications()}
        records = self.rows("SELECT * FROM commands WHERE action_type='application' AND enabled=1")
        records.sort(key=lambda row: (not row['is_builtin'], row['name'].casefold(), row['id']))
        entries = {}
        for record in records:
            try:
                target = json.loads(record['action_config'])['target']
                if not isinstance(target, str) or target in entries:
                    continue
                if target in WindowsLauncher.SUPPORTED_APPS:
                    name = APPLICATION_NAMES.get(target, target)
                else:
                    app = applications.get(target)
                    if app is None or not app.enabled or app.needs_repair:
                        continue
                    name = app.name
                if not self.rows('SELECT id FROM command_phrases WHERE command_id=? LIMIT 1', (record['id'],)):
                    continue
                aliases = tuple(sorted(self._application_aliases.get(target, ())))
                entries[target] = ApplicationShortcut(target, name, aliases, record['id'])
            except (ValueError, KeyError, TypeError):
                continue
        return match_shortcuts(entries.values(), query)

    def execute_application_shortcut(self, target):
        """Resolve a live target ID; a displayed suggestion grants no lasting authority."""
        self.memory_conversation.clear()
        self.file_session.clear()
        entry = next((item for item in self.application_shortcuts() if item.target == target), None)
        if entry is None:
            interpretation = InterpretationResult(reason=MatchReason.UNAVAILABLE_COMMAND)
        else:
            interpretation = InterpretationResult(True, CommandIntent(IntentType.OPEN_APPLICATION, target),
                entry.command_id, MatchReason.SMART_MATCH, 1.0)
        return self._execute_registered_command(interpretation, '', expected_application=target)

    def list_registered_applications(self):
        return [RegisteredApplication(**dict(row, enabled=bool(row['enabled']), needs_repair=bool(row['needs_repair']),
                aliases=tuple(item['alias'] for item in self.rows('SELECT alias FROM application_aliases WHERE application_id=? ORDER BY rowid', (row['id'],)))))
                for row in self.rows('SELECT * FROM registered_applications ORDER BY name')]

    def get_registered_application(self, application_id):
        return next((app for app in self.list_registered_applications() if app.id == application_id), None)

    def _validate_command_action(self, action, target, connection=None):
        connection = connection or self.db
        if action == "routine" and isinstance(target, str):
            if connection.execute("SELECT id FROM routines WHERE id=?", (target,)).fetchone() or (connection is self.db and target == self._routine_creation):
                return
        if action == 'application' and isinstance(target, str) and connection.execute(
                'SELECT id FROM registered_applications WHERE id=?', (target,)).fetchone():
            return
        self.validate_action(action, target)

    def _write_application_aliases(self, application_id, aliases):
        if not isinstance(aliases, (list, tuple)) or not 1 <= len(aliases) <= 30:
            raise ValueError('Enter 1–30 aliases.')
        reserved = {alias for names in (*APPLICATION_ALIASES.values(), *WEBSITE_ALIASES.values()) for alias in names}
        prepared = [normalize(text(alias, 'Alias', 150)) for alias in aliases]
        if len(set(prepared)) != len(prepared) or any(alias in reserved or not normalize_input(alias).valid for alias in prepared):
            raise ValueError('Aliases must be unique and cannot conflict with built-in applications or websites.')
        for alias in prepared:
            if self.rows('SELECT id FROM application_aliases WHERE normalized_alias=? AND application_id<>?', (alias, application_id)):
                raise ValueError('Application alias already registered: ' + alias)
        self.db.execute('DELETE FROM application_aliases WHERE application_id=?', (application_id,))
        for alias in prepared:
            self.db.execute('INSERT INTO application_aliases VALUES (?,?,?,?,?)', (identifier(), application_id, alias, alias, now()))

    def register_application(self, candidate, aliases=None, command_name=None, phrases=None, *, notify=True):
        """Register after individual Add or the user-authorized bulk Refresh action."""
        if not isinstance(candidate, DiscoveredApplication):
            raise ValueError('Choose a discovered application.')
        candidate = ApplicationValidator().validate(candidate)
        if not candidate.launchable:
            raise ValueError('This application cannot be registered: ' + candidate.validation_status.value)
        name = text(candidate.name, 'Application name', 150)
        path = canonical_path(candidate.executable_path)
        if any(canonical_path(app.executable_path) == path for app in self.list_registered_applications()):
            raise ValueError('This application is already registered.')
        application_id, stamp = 'app-' + identifier(), now()
        with self.db:
            self.db.execute('INSERT INTO registered_applications VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                            (application_id, name, normalize(name), candidate.executable_path, candidate.publisher,
                             candidate.version, candidate.icon_path, ','.join(source.value for source in candidate.sources or (candidate.source,)),
                             1, 0, stamp, stamp))
            self._write_application_aliases(application_id, aliases if aliases is not None else [name])
            if phrases is not None:
                self._write_command(identifier(), command_name or 'Open ' + name, 'application', application_id, phrases)
        if notify:
            self.changed()
        logger.info('Application registered')
        return application_id

    def register_discovered_applications(self, candidates):
        """User-clicked Refresh authorizes valid registrations; no executable is launched."""
        applications = self.list_registered_applications()
        paths = {canonical_path(app.executable_path): app for app in applications}
        commands = self.commands()
        targets = {command['target'] for command in commands if command['action_type'] == 'application'}
        used_phrases = {normalize(phrase) for command in commands for phrase in command['phrases']}
        used_aliases = {alias for names in (*APPLICATION_ALIASES.values(), *WEBSITE_ALIASES.values()) for alias in names}
        used_aliases.update(alias for app in applications for alias in app.aliases)
        summary = dict(added=0, already_added=0, commands_created=0, invalid=0, failed=0)
        changed = False
        for candidate in candidates:
            try:
                candidate = ApplicationValidator().validate(candidate)
                if not candidate.launchable:
                    summary['invalid'] += 1
                    continue
                path = canonical_path(candidate.executable_path)
                existing = paths.get(path)
                if existing and existing.id in targets:
                    summary['already_added'] += 1
                    continue
                base = normalize(candidate.name)[:120]
                request = normalize_input('open ' + base)
                if not base or not request.valid or request.negated:
                    base = 'application'
                alias, suffix = base, 1
                def phrases_for(value):
                    return [verb + ' ' + value for verb in ('open', 'launch', 'start')]
                while alias in used_aliases or any(phrase in used_phrases for phrase in phrases_for(alias)):
                    alias = base + (' app' if suffix == 1 else f' app {suffix}')
                    suffix += 1
                phrases = phrases_for(alias)
                if existing:
                    with self.db:
                        self._write_command(identifier(), 'Open ' + alias.title(), 'application', existing.id, phrases)
                    summary['already_added'] += 1
                    application_id = existing.id
                else:
                    candidate = replace(candidate, name=candidate.name.strip()[:150])
                    application_id = self.register_application(candidate, aliases=[alias],
                        command_name='Open ' + alias.title(), phrases=phrases, notify=False)
                    summary['added'] += 1
                    paths[path] = self.get_registered_application(application_id)
                targets.add(application_id)
                used_aliases.add(alias)
                used_phrases.update(phrases)
                summary['commands_created'] += 1
                changed = True
            except (ValueError, sqlite3.Error):
                summary['failed'] += 1
        if changed:
            self.changed()
        logger.info('Refresh registration completed: %d added, %d existing, %d invalid, %d failed',
                    summary['added'], summary['already_added'], summary['invalid'], summary['failed'])
        return summary

    def update_application(self, application_id, name, aliases):
        if not self.get_registered_application(application_id):
            raise ValueError('Application is no longer registered.')
        name = text(name, 'Application name', 150)
        with self.db:
            self._write_application_aliases(application_id, aliases)
            self.db.execute('UPDATE registered_applications SET name=?,normalized_name=?,updated_at=? WHERE id=?',
                            (name, normalize(name), now(), application_id))
        self.changed()

    def set_application_enabled(self, application_id, enabled):
        app = self.get_registered_application(application_id)
        if app is None:
            raise ValueError('Application is no longer registered.')
        if enabled and ApplicationValidator.validate_registered_path(app.executable_path)[0] != ValidationStatus.VALID:
            raise ValueError('The executable needs repair. Rediscover and approve it again.')
        with self.db:
            self.db.execute('UPDATE registered_applications SET enabled=?,needs_repair=?,updated_at=? WHERE id=?',
                            (int(bool(enabled)), 0 if enabled else int(app.needs_repair), now(), application_id))
        self.changed()

    def unregister_application(self, application_id):
        # Keep phrases/history but disable associated commands. Installed files are untouched.
        with self.db:
            for command in self.commands():
                if command['action_type'] == 'application' and command['target'] == application_id:
                    self.db.execute('UPDATE commands SET enabled=0,updated_at=? WHERE id=?', (now(), command['id']))
            self.db.execute('DELETE FROM registered_applications WHERE id=?', (application_id,))
        self.changed()
        logger.info('Application registration removed; related commands disabled')

    def _refresh_application_aliases(self):
        aliases = {key: set(names) for key, names in APPLICATION_ALIASES.items()}
        applications = self.list_registered_applications()
        display_counts = Counter(normalize(app.name) for app in applications)
        reserved = {name for group in (*APPLICATION_ALIASES.values(), *WEBSITE_ALIASES.values()) for name in group}
        for app in applications:
            names = set(app.aliases)
            display_name = normalize(app.name)
            if (display_counts[display_name] == 1 and display_name not in reserved
                    and not any(display_name in other.aliases for other in applications if other.id != app.id)):
                names.add(display_name)
            # Reuse simple open/launch/start command phrases as aliases where practical.
            for command in self.commands():
                if command['action_type'] == 'application' and command['target'] == app.id:
                    for phrase in command['phrases']:
                        match = re.fullmatch(r'(?:open|launch|start) (.+)', normalize_input(phrase).text)
                        if match:
                            names.add(match[1])
            aliases[app.id] = names
        self._application_aliases = aliases
        if isinstance(self.interpreter, RuleBasedIntentInterpreter):
            self.interpreter.application_aliases = aliases

    def _write_command(self, command_id, name, action, target, phrases, enabled=True, builtin=False):
        name = text(name, 'Command name', 150)
        self._validate_command_action(action, target)
        if not isinstance(phrases, list) or not 1 <= len(phrases) <= 30:
            raise ValueError('Enter 1–30 phrases.')
        if action == "routine" and any(not normalize_input(p).valid or normalize_input(p).negated or p.strip().startswith("@") for p in phrases):
            raise ValueError("Routine phrases must be usable exact commands without negation or shortcuts.")
        normalized = [normalize(text(p, 'Phrase', 200)) for p in phrases]
        if len(set(normalized)) != len(normalized):
            raise ValueError('Duplicate phrases in this command.')
        if any(p.startswith('/') or p == 'help' or p.startswith('remember my name as ') or
               ((intent := self.interpreter.interpret(p).intent) is not None and
                intent.intent in (IntentType.MEMORY_STORE, IntentType.MEMORY_QUERY, IntentType.MEMORY_FORGET, IntentType.FILE_SEARCH)) for p in normalized):
            raise ValueError('This phrase is reserved for memory, help or local file search.')
        for phrase in normalized:
            if self.rows('SELECT id FROM command_phrases WHERE normalized_phrase=? AND command_id<>?', (phrase, command_id)):
                raise ValueError(f'Phrase already registered: {phrase}')
        stamp = now()
        self.db.execute('''INSERT INTO commands VALUES (?,?,?, ?,?,?,?, ?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,action_type=excluded.action_type,action_config=excluded.action_config,enabled=excluded.enabled,updated_at=excluded.updated_at''',
            (command_id, name, '', action, json.dumps(dict(target=target)), '', '', int(bool(enabled)), int(builtin), stamp, stamp))
        self.db.execute('DELETE FROM command_phrases WHERE command_id=?', (command_id,))
        for phrase, normalized_phrase in zip(phrases, normalized):
            self.db.execute('INSERT INTO command_phrases VALUES (?,?,?,?,?)', (identifier(), command_id, phrase.strip(), normalized_phrase, stamp))

    def save_command(self, name, action, target, phrases, enabled=True, command_id=None):
        routine = self.rows("SELECT id FROM routines WHERE command_id=?", (command_id,))
        if routine:
            self.workflows.ensure_idle(routine[0]["id"])
            if action != "routine" or target != routine[0]["id"]:
                raise ValueError("Edit this routine in Workflows.")
        elif action == "routine":
            raise ValueError("Create routine commands in Workflows.")
        with self.db:
            self._write_command(command_id or identifier(), name, action, target, phrases, enabled)
        self.changed()

    def delete_command(self, command_id):
        routine = self.rows("SELECT id FROM routines WHERE command_id=?", (command_id,))
        if routine:
            self.workflows.ensure_idle(routine[0]["id"])
        with self.db:
            self.db.execute('DELETE FROM commands WHERE id=?', (command_id,))
        self.changed()

    def propose_memory(self, value):
        return text(value, 'Name', 150)

    def confirm_name(self, value):
        category = next(c['id'] for c in self.categories() if c['name'] == 'Personal Information')
        existing = self.memory_service.find_existing('user.name')
        return self.memory_service.save_memory(category, 'My name', 'user.name', self.propose_memory(value),
            memory_id=existing['id'] if existing else None, confirmed=True,
            memory_type='PROFILE', source='COMMAND')

    def propose_memory_intent(self, intent):
        """Stage an explicit write/delete for one runtime, without persisting its payload."""
        key = text(intent.target, 'Memory key', 200)
        existing = self.memory_service.find_existing(key)
        if existing:
            key = existing['memory_key']
        if existing and existing['sensitive']:
            raise ValueError('Use the Memory Manager to change sensitive memories.')
        if existing and ((existing['memory_scope'] == 'PROFILE' and existing['scope_id'] != self.memory_service.profile_id) or
                         (existing['memory_scope'] == 'PET_PROFILE' and existing['scope_id'] != self.active_profile()['id'])):
            raise ValueError('This memory belongs to another profile. Review it in the Memory Manager.')
        operation = 'delete' if intent.intent == IntentType.MEMORY_FORGET else 'save'
        if operation == 'delete' and not existing:
            return dict(success=False, message='That memory has not been saved.', pet_state='idle')
        value = None if operation == 'delete' else text(intent.value, 'Memory value', 20000)
        if key == 'user.name' and value is not None:
            value = self.propose_memory(value)
        stamp = time.monotonic()
        self._memory_confirmations = {token: draft for token, draft in self._memory_confirmations.items()
                                      if stamp - draft['created'] < 300}
        if len(self._memory_confirmations) >= 100:
            self._memory_confirmations.clear()
        token = identifier()
        self._memory_confirmations[token] = dict(operation=operation, key=key, value=value,
            memory_type=getattr(intent, 'memory_type', None) or ('PROFILE' if key.startswith('user.') else 'KNOWLEDGE'),
            existing_id=existing['id'] if existing else None,
            revision=existing['updated_at'] if existing else None, created=stamp,
            profile_id=self.memory_service.profile_id, pet_profile_id=self.active_profile()['id'],
            session_id=self.memory_service.session_id)
        message = f'Forget {key}?' if operation == 'delete' else (
            f'Replace {key} with the supplied value?' if existing else f'Save {key}?')
        if key == 'user.name' and operation == 'save':
            message = f'Save your name as {value}?'
        result = dict(success=False, message=message, memory_confirmation=token, pet_state='thinking')
        # Preserve the public legacy name proposal while the controller uses the guarded token.
        if key == 'user.name' and operation == 'save':
            result['confirmation'] = value
        return result

    def confirm_memory(self, token):
        draft = self._memory_confirmations.pop(token, None)
        if not draft or time.monotonic() - draft['created'] >= 300:
            raise ValueError('This memory confirmation expired. Submit the request again.')
        if (draft['profile_id'] != self.memory_service.profile_id or
                draft['pet_profile_id'] != self.active_profile()['id'] or
                draft['session_id'] != self.memory_service.session_id):
            raise ValueError('The memory profile changed. Submit the request again.')
        existing = self.memory_service.find_existing(draft['key'])
        if ((existing['id'] if existing else None) != draft['existing_id'] or
                (existing['updated_at'] if existing else None) != draft['revision']):
            raise ValueError('This memory changed. Review it and submit the request again.')
        if draft['operation'] == 'delete':
            self.delete_memory(existing['id'])
            return dict(success=True, message='Memory deleted.', pet_state='success')
        memory_type = draft['memory_type']
        category_name = 'Personal Information' if memory_type == 'PROFILE' else 'Important Notes'
        category_id = next(c['id'] for c in self.categories() if c['name'] == category_name)
        metadata = dict(memory_type=memory_type, source='COMMAND')
        if memory_type == 'CONTEXT':
            metadata.update(memory_scope='SESSION', lifetime='session')
        self.memory_service.save_memory(category_id, draft['key'], draft['key'], draft['value'],
            memory_id=existing['id'] if existing else None, confirmed=True, **metadata)
        return dict(success=True, message='Your name is saved.' if draft['key'] == 'user.name' else 'Memory saved.', pet_state='success')

    def cancel_memory_confirmation(self, token):
        self._memory_confirmations.pop(token, None)

    def resolve_voice_phrase(self, phrase):
        """Compatibility helper; live typed and speech submission use interpret() directly."""
        if not isinstance(phrase, str) or len(phrase) > 500:
            return phrase
        parsed = self.interpret(phrase)
        if parsed.intent and parsed.intent.intent in (IntentType.MEMORY_STORE, IntentType.MEMORY_QUERY, IntentType.MEMORY_FORGET):
            return phrase
        normalized = normalize(phrase)
        if self.rows('SELECT id FROM command_phrases WHERE normalized_phrase=?', (normalized,)):
            return phrase
        translated = normalize_input(phrase).text
        # A canonical registered phrase also wins, especially when disabled.
        if self.rows('SELECT id FROM command_phrases WHERE normalized_phrase=?', (normalize(translated),)):
            return translated
        result = self.interpret(phrase)
        if result.matched and result.command_id and result.intent.intent in (IntentType.OPEN_APPLICATION, IntentType.OPEN_WEBSITE):
            return self.rows('SELECT phrase FROM command_phrases WHERE command_id=? ORDER BY rowid', (result.command_id,))[0]['phrase']
        return translated

    def _registered_interpretation(self, phrase, reason):
        found = self.rows('''SELECT c.* FROM commands c JOIN command_phrases p ON p.command_id=c.id
                            WHERE p.normalized_phrase=?''', (normalize(phrase),))
        if not found:
            return None
        record = found[0]
        if record['action_type'] == 'routine' and reason != MatchReason.EXACT_PHRASE:
            return None
        intent = self.intent_resolver.command_intent(record)
        return InterpretationResult(bool(record['enabled']), intent, record['id'],
                                    reason if record['enabled'] else MatchReason.DISABLED_COMMAND,
                                    1.0 if reason == MatchReason.EXACT_PHRASE else 0.98)

    def interpret(self, phrase):
        """Parse only: no OS calls, database writes, history, or memory decryption."""
        normalized_input = normalize_input(phrase)
        if not normalized_input.valid:
            return InterpretationResult(reason=MatchReason.INVALID_INPUT)
        local = file_intent(phrase)
        if local and (phrase.strip().startswith('/') or local.action == 'CANCEL'):
            return InterpretationResult(True, local, reason=MatchReason.SMART_MATCH, confidence=1.0)
        # Mandatory safety veto precedes matching, even for an exact custom phrase.
        if normalized_input.negated:
            return InterpretationResult(reason=MatchReason.NEGATED_COMMAND)
        if phrase.strip().startswith('@'):
            query = normalize(phrase.strip()[1:])
            exact = [entry for entry in self.application_shortcuts(query) if query and
                     query in {normalize(name) for name in (entry.display_name, *entry.aliases)}]
            if len(exact) != 1:
                return InterpretationResult(reason=MatchReason.AMBIGUOUS_TARGET if exact else MatchReason.UNAVAILABLE_COMMAND)
            entry = exact[0]
            return InterpretationResult(True, CommandIntent(IntentType.OPEN_APPLICATION, entry.target),
                entry.command_id, MatchReason.SMART_MATCH, 1.0)
        normalized = normalize(phrase)
        if normalized in ('help', 'what is my name'):
            kind = IntentType.SHOW_HELP if normalized == 'help' else IntentType.MEMORY_QUERY
            intent = CommandIntent(kind, 'user.name' if kind == IntentType.MEMORY_QUERY else None, source='reserved')
            return InterpretationResult(True, intent, reason=MatchReason.EXACT_PHRASE, confidence=1.0)
        memory = re.fullmatch(r'remember\s+my\s+name\s+as\s+(.+)', phrase.strip(), re.IGNORECASE)
        if memory:
            intent = CommandIntent(IntentType.MEMORY_STORE, 'user.name', memory[1], source='reserved')
            return InterpretationResult(True, intent, reason=MatchReason.EXACT_PHRASE, confidence=1.0)
        result = self.interpreter.interpret(phrase)
        # Explicit memory grammar stays reserved even in a pre-upgrade registry.
        if result.matched and result.intent and result.intent.intent in (IntentType.MEMORY_STORE, IntentType.MEMORY_QUERY, IntentType.MEMORY_FORGET, IntentType.FILE_SEARCH):
            if not AUTO_EXECUTE_THRESHOLD <= result.intent.confidence <= 1.0:
                return InterpretationResult(False, result.intent, reason=MatchReason.LOW_CONFIDENCE, confidence=result.intent.confidence)
            return result
        registered = self._registered_interpretation(phrase, MatchReason.EXACT_PHRASE)
        if registered is not None:
            return registered
        translated = normalize_mixed_voice(phrase)
        registered = self._registered_interpretation(translated, MatchReason.VOICE_NORMALIZED)
        if registered is not None:
            return registered
        if not result.matched:
            if result.reason != MatchReason.UNKNOWN_INTENT:
                return result
            result = browser_fallback(phrase, normalized_input)
            if not result.matched:
                return result
            if result.intent.source == DIRECT_WEBSITE_SOURCE:
                return result
        if result.intent is None:
            return InterpretationResult(reason=MatchReason.UNKNOWN_INTENT)
        if result.intent.intent in (IntentType.MEMORY_STORE, IntentType.MEMORY_QUERY, IntentType.MEMORY_FORGET, IntentType.SHOW_HELP):
            if not AUTO_EXECUTE_THRESHOLD <= result.intent.confidence <= 1.0:
                return InterpretationResult(False, result.intent, reason=MatchReason.LOW_CONFIDENCE, confidence=result.intent.confidence)
            return result
        if result.intent.intent == IntentType.PLAY_MEDIA:
            result = replace(result, intent=replace(result.intent,
                target=self.app_settings()['default_music_player'] if result.intent.source == 'music_default' else result.intent.target))
        return self.memory_resolver.resolve(result.intent, self.commands(), self._application_aliases)

    @staticmethod
    def interpretation_message(result):
        """Fixed responses never echo an unsupported raw input or private payload."""
        if result.reason == MatchReason.NEGATED_COMMAND:
            return 'Command cancelled. Nothing was executed.'
        if result.reason == MatchReason.DISABLED_COMMAND:
            return 'That command is disabled. Enable it in the Manager to use it.'
        if result.reason in (MatchReason.AMBIGUOUS_TARGET, MatchReason.AMBIGUOUS_COMMAND):
            return 'I found more than one possible match. Please use a registered phrase.'
        if result.reason == MatchReason.LOW_CONFIDENCE:
            names = {'vscode': 'VS Code', 'chrome': 'Chrome', 'explorer': 'File Explorer'}
            name = names.get(result.intent.target, 'the registered command')
            return f'Did you mean "Open {name}"?'
        if result.reason == MatchReason.UNAVAILABLE_COMMAND:
            return 'I understood your request, but that command is not currently available.'
        if result.reason == MatchReason.INVALID_INPUT:
            return 'Use a command of at most 500 characters without control characters.'
        return 'Unsupported command. Type help to see registered phrases.'

    def execute(self, phrase, defer_browser=False, defer_file_search=False):
        self.memory_conversation.clear()
        interpretation = self.interpret(phrase)
        if interpretation.reason == MatchReason.INVALID_INPUT:
            self.file_session.clear()
            return dict(success=False, message=self.interpretation_message(interpretation), pet_state='error')
        intent = interpretation.intent if interpretation.matched else None
        if intent and intent.intent == IntentType.PLAY_MEDIA and not intent.value:
            return dict(success=False, message='Please specify a song name.', pet_state='thinking')
        if intent and intent.intent == IntentType.RUN_ROUTINE:
            return dict(success=True, message="Starting routine…", pet_state="working", routine_id=intent.target, routine_phrase=normalize(phrase))
        if intent and intent.intent == IntentType.FILE_SEARCH:
            if intent.action in ('FIND', 'FIND_AND_OPEN'):
                if not valid_query(intent.query):
                    self.file_session.clear()
                    return FileSearchSession.reply(False, 'Type / followed by a file name, or a name followed by folder. Use names without path separators or wildcards.')
                token = self.file_session.begin()
                if defer_file_search:
                    return dict(success=True, message='Searching local files…', pet_state='working',
                                file_search=True, file_search_intent=intent, file_search_token=token)
                try:
                    response = self.file_search.search(intent)
                    if isinstance(self.file_search, FileSearchService):
                        response = self.file_search.merge_activity(response, intent, self.file_open_records())
                except Exception:
                    response = FileSearchResponse(partial=True, notice='File search could not finish. Review Settings → Local file search.')
                return self.finish_file_search(token, intent, response)
            return self.file_session.present(self.file_session.followup(intent, self.launcher))
        self.file_session.clear()
        if intent and intent.intent == IntentType.MEMORY_QUERY:
            try:
                if intent.source == 'memory_panel':
                    if intent.action == 'LIST' and intent.target in ('password', 'card'):
                        rows = matching_memories(self.memory_service, None, intent.target)
                        return self.memory_conversation.begin(rows, intent.target, listing=True)
                    options = dict(intent.filters)
                    kind, field = options.get('kind'), options.get('field') or None
                    if (intent.action != 'LOOKUP' or kind not in ('password', 'card')
                            or not isinstance(intent.target, str) or not 1 <= len(intent.target) <= 200
                            or field not in (None, 'card_number', 'cvv', 'expiry')):
                        raise ValueError('Invalid memory query.')
                    rows = matching_memories(self.memory_service, intent.target, kind)
                    return self.memory_conversation.begin(rows, kind, field=field)
                is_pref = bool(intent.target and intent.target.startswith('preferred.'))
                memory = self.get_memory_by_key(intent.target, consume=False)
                if memory and memory['sensitive'] and not is_pref:
                    return self.memory_conversation.begin([memory], memory_kind(memory))
            except ValueError:
                self.memory_conversation.clear()
                return dict(success=False, message='This memory is unavailable. Review it in the Memory Manager.', pet_state='error')
            if not memory:
                message = ('Your name has not been saved.' if intent.target == 'user.name' else 'That memory has not been saved.')
            elif memory['sensitive']:
                message = 'Sensitive memory is saved. Reveal it in the Memory Manager.'
            else:
                message = memory['memory_value']
            if memory:
                self.memory_service.record_access(memory['id'])
            return dict(success=bool(memory), message=message, pet_state='success' if memory else 'idle')
        if intent and intent.intent in (IntentType.MEMORY_STORE, IntentType.MEMORY_FORGET):
            try:
                return self.propose_memory_intent(intent)
            except ValueError as error:
                return dict(success=False, message=str(error), pet_state='error')
        if intent and intent.intent == IntentType.SHOW_HELP:
            names = [c['phrases'][0] for c in self.commands() if c['enabled']]
            return dict(success=True, message='Commands: ' + ', '.join(names) + '\nFiles: /<name>; find <name>; find <name> folder; open it; yes; show results; open <number>\nBrowser: search <query>; plain text searches Google; amazon.com opens a website; play <song>; play <song> on spotify; play <song> on youtube\nMemory: remember my name as <name>; save my preferred browser as <app>; what is my editor; forget my preferred browser; my <name> password; list my passwords; list my card details', pet_state='idle')
        if intent and intent.intent == IntentType.OPEN_WEBSITE and intent.source == DIRECT_WEBSITE_SOURCE:
            # Revalidate at dispatch, even if an interpreter supplies forged metadata.
            try:
                target = website_url(intent.target)
                if target is None:
                    raise ValueError('Invalid website address.')
                self.validate_action('url', target)
            except (ValueError, OSError):
                return self.finish_browser_action('url', False, 'Invalid website address.')
            if defer_browser:
                return dict(success=True, message='Opening website…', pet_state='working',
                            browser_action='url', browser_target=target)
            try:
                success, message = self.launcher.open_registered_url(target)
            except Exception:
                success, message = False, 'The browser action could not be executed.'
            return self.finish_browser_action('url', success, message)
        return self._execute_registered_command(interpretation, phrase, defer_browser)

    def finish_file_search(self, token, intent, response):
        """Apply a worker response only to the still-current in-memory conversation."""
        if self.file_session.active() and token == self.file_session.token:
            # Pet history candidates were validated in the worker; no filesystem I/O here.
            items = sorted(response.results, key=FileSearchSession.opened_key)
            response = replace(response, results=tuple(items[:200]), partial=response.partial or len(items) > 200)
        return self.file_session.finish(token, response, intent, self.launcher)

    def file_open_records(self):
        return {row[0]: row[1] for row in self.db.execute("SELECT path, opened FROM file_open_history ORDER BY opened DESC LIMIT 2000")}

    def _record_file_open(self, item, stamp):
        with self.db:
            self.db.execute('INSERT INTO file_open_history VALUES (?,?) ON CONFLICT(path) DO UPDATE SET opened=excluded.opened', (item.path, stamp))
            self.db.execute('DELETE FROM file_open_history WHERE path NOT IN (SELECT path FROM file_open_history ORDER BY opened DESC LIMIT 2000)')

    def open_file_result(self, token, result_id):
        return self.file_session.open_identified(token, result_id, self.launcher)

    def sort_file_results(self, token, order):
        return self.file_session.sort_results(token, order)


    def file_search_settings(self):
        config = self.get_setting('file_search', dict(roots=[], everything_executable=''))
        self.validate_file_search_settings(config)
        return config

    @staticmethod
    def validate_file_search_settings(config):
        from ..services.file_search import is_local_path
        if not isinstance(config, dict) or set(config) != {'roots', 'everything_executable'}:
            raise ValueError('Invalid local file search settings.')
        roots, executable = config['roots'], config['everything_executable']
        if not isinstance(roots, list) or len(roots) > 32 or any(not isinstance(root, str) or not is_local_path(root) for root in roots):
            raise ValueError('Choose up to 32 absolute folders on local disks.')
        if not isinstance(executable, str) or (executable and (not is_local_path(executable) or Path(executable).name.casefold() != 'es.exe')):
            raise ValueError('Choose the Everything command-line client es.exe on a local disk.')

    def create_file_search_service(self):
        try:
            config = self.file_search_settings()
        except ValueError:
            # Invalid imported configuration must never expand scope or execute a path.
            return FileSearchService(roots=[])
        return FileSearchService(roots=config['roots'] or None,
            everything_executable=config['everything_executable'] or None,
            integration_dir=self.root / 'integrations/everything')

    def save_file_search_settings(self, roots, everything_executable=''):
        config = dict(roots=list(roots), everything_executable=everything_executable.strip())
        self.validate_file_search_settings(config)
        config['roots'] = [str(local_path(root)) for root in config['roots']]
        if any(not Path(root).is_dir() for root in config['roots']):
            raise ValueError('Choose existing search folders.')
        if config['everything_executable']:
            config['everything_executable'] = str(local_path(config['everything_executable']))
            if not Path(config['everything_executable']).is_file():
                raise ValueError('Choose the es.exe file.')
        with self.db:
            self.db.execute('INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                            ('file_search', json.dumps(config)))
        self.file_session.clear()
        self.file_search = self.create_file_search_service()
        self.changed()

    def _execute_registered_command(self, interpretation, phrase, defer_browser=False, expected_application=None):
        """Shared live validation, OS dispatch and private history for resolved commands."""
        intent = interpretation.intent if interpretation.matched else None
        found = self.rows('SELECT * FROM commands WHERE id=? AND enabled=1', (interpretation.command_id,)) if interpretation.matched else []
        command_id = None
        if not found:
            success, message = False, self.interpretation_message(interpretation)
        else:
            record = found[0]
            command_id = record['id']
            try:
                target = json.loads(record['action_config'])['target']
                if expected_application is not None and (record['action_type'] != 'application' or target != expected_application):
                    raise ValueError('The selected application command changed.')
                self._validate_command_action(record['action_type'], target)
                if intent.intent in (IntentType.WEB_SEARCH, IntentType.PLAY_MEDIA):
                    action = 'search' if intent.intent == IntentType.WEB_SEARCH else 'music'
                    if not intent.value or any(ord(c) < 32 for c in phrase):
                        raise ValueError('Invalid browser value.')
                    if defer_browser:
                        return dict(success=True, message='Searching…' if action == 'search' else 'Finding your song…',
                                    pet_state='working', browser_action=action, browser_target=intent.value,
                                    music_provider=intent.target if action == 'music' else None,
                                    music_open_mode=self.app_settings()['spotify_open_mode'])
                    try:
                        if action == 'music':
                            success, message = self.launcher.play_music(intent.value, provider=intent.target,
                                open_mode=self.app_settings()['spotify_open_mode'])
                        else:
                            success, message = self.launcher.search_web(intent.value)
                    except Exception:
                        success, message = False, 'The browser action could not be executed.'
                    return self.finish_browser_action(action, success, message)
                elif record['action_type'] == 'application':
                    app = self.get_registered_application(target)
                    if app and not app.enabled:
                        success, message = False, f'{app.name} is currently disabled.'
                    elif app and (app.needs_repair or ApplicationValidator.validate_registered_path(app.executable_path)[0] != ValidationStatus.VALID):
                        success, message = False, f'{app.name} could not be found or is unsafe. Rediscover it in Commands.'
                    else:
                        if interpretation.memory_id:
                            if self.memory_retriever.consume(interpretation.memory_id) is None:
                                raise ValueError('The stored preference is no longer available.')
                        success, message = self.launcher.open_application(target)
                else:
                    success, message = self.launcher.open_registered_url(target)
            except Exception:
                success, message = False, 'The configured action could not be executed.'
        # Unsupported input and memory contents never enter history/logs.
        trigger = '[unsupported command]'
        if found:
            trigger = normalize(phrase) if interpretation.reason == MatchReason.EXACT_PHRASE else normalize(
                self.rows('SELECT phrase FROM command_phrases WHERE command_id=? ORDER BY rowid', (command_id,))[0]['phrase'])
        with self.db:
            self.db.execute('INSERT INTO command_history VALUES (?,?,?,?,?,?)', (identifier(), command_id, trigger, 'success' if success else 'failed', '' if success else message, now()))
        self.changed()
        return dict(success=success, message=message, pet_state='success' if success else 'error')

    def finish_browser_action(self, action, success, message):
        # Keep queries, song titles and direct website addresses out of history.
        trigger = {'search': '[web search]', 'music': '[music playback]', 'url': '[website open]'}[action]
        with self.db:
            self.db.execute('INSERT INTO command_history VALUES (?,?,?,?,?,?)',
                            (identifier(), None, trigger,
                             'success' if success else 'failed', '' if success else 'Browser action failed.', now()))
        self.changed()
        return dict(success=success, message=message, pet_state='success' if success else 'error')

    def history(self, status='', date='', command_id=None):
        sql = '''SELECT h.*, COALESCE(c.name, CASE h.trigger_phrase WHEN '[web search]' THEN 'Web search' WHEN '[music playback]' THEN 'Music playback' WHEN '[website open]' THEN 'Website open' ELSE 'Unsupported / deleted command' END) AS name FROM command_history h LEFT JOIN commands c ON c.id=h.command_id WHERE 1=1'''
        args = []
        if status:
            sql += ' AND h.execution_status=?'
            args.append(status)
        if command_id:
            sql += ' AND h.command_id=?'
            args.append(command_id)
        records = self.rows(sql + ' ORDER BY h.executed_at DESC LIMIT 1000', args)
        if date:
            records = [r for r in records if datetime.fromisoformat(r['executed_at']).astimezone().date().isoformat() == date]
        return records

    def clear_history(self):
        self.workflows.ensure_idle()
        with self.db:
            self.db.execute('DELETE FROM workflow_runs')
            self.db.execute('DELETE FROM command_history')
        self.changed()

    def stats(self):
        today = datetime.now().astimezone().date()
        count = sum(datetime.fromisoformat(r['executed_at']).astimezone().date() == today for r in self.rows('SELECT executed_at FROM command_history'))
        return dict(memories=self.db.execute('SELECT count(*) FROM memories').fetchone()[0], commands=self.db.execute('SELECT count(*) FROM commands').fetchone()[0], today=count)

    def assets(self):
        return self.rows('SELECT * FROM pet_assets ORDER BY imported,name')

    def asset_path(self, asset_id):
        rows = self.rows('SELECT * FROM pet_assets WHERE id=?', (asset_id,))
        if not rows:
            raise ValueError('Unknown pet asset.')
        asset = rows[0]
        root = self.root / 'pets/imported' if asset['imported'] else settings.PET_IMAGE_DIR
        path = (root / asset['filename']).resolve()
        if path.parent != root.resolve() or path.suffix.lower() != '.png' or not path.is_file():
            raise ValueError('Invalid or missing pet asset.')
        return path

    def import_asset(self, source):
        from PIL import Image
        source = Path(source)
        if source.suffix.lower() != '.png' or source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Choose a PNG sprite sheet under 8 MB.')
        with Image.open(source) as img:
            if img.format != 'PNG' or not 16 <= img.height <= 512 or img.width % img.height or not 1 <= img.width // img.height <= 64:
                raise ValueError('Use a horizontal sheet of 1–64 square frames, 16–512 pixels high.')
            img.load()
            asset_id = identifier()
            filename = asset_id + '.png'
            img.convert('RGBA').save(self.root / 'pets/imported' / filename)
        with self.db:
            self.db.execute('INSERT INTO pet_assets VALUES (?,?,?,1)', (asset_id, text(source.stem, 'Asset name', 100), filename))
        self.changed()
        return asset_id

    @staticmethod
    def validate_pet(config):
        if not isinstance(config, dict) or set(config) != set(DEFAULT_PET):
            raise ValueError('Invalid pet configuration fields.')
        for key, low, high in [('size', 96, 400), ('chat_width', 260, 600), ('text_size', 10, 24), ('radius', 0, 30)]:
            if type(config[key]) is not int or not low <= config[key] <= high:
                raise ValueError(f'{key} must be between {low} and {high}.')
        for key in ('x', 'y'):
            if config[key] is not None and (type(config[key]) is not int or abs(config[key]) > 100000):
                raise ValueError('Invalid desktop position.')
        if type(config['opacity']) not in (int, float) or not 0.2 <= config['opacity'] <= 1:
            raise ValueError('Opacity must be 0.2–1.')
        if any(type(config[key]) is not bool for key in ('animations', 'always_on_top')):
            raise ValueError('Invalid pet flags.')
        if not isinstance(config['background'], str) or not re.fullmatch('#[0-9a-fA-F]{6}', config['background']):
            raise ValueError('Use a six-digit hex background color.')

    def profiles(self):
        rows = self.rows('SELECT * FROM pet_profiles ORDER BY created_at')
        for row in rows:
            row['config'] = json.loads(self.rows('SELECT config FROM pet_settings WHERE profile_id=?', (row['id'],))[0]['config'])
        return rows

    def active_profile(self):
        return next(p for p in self.profiles() if p['is_active'])

    def _write_profile(self, profile_id, name, asset_id, config, active):
        self.validate_pet(config)
        if not self.rows('SELECT id FROM pet_assets WHERE id=?', (asset_id,)):
            raise ValueError('Unknown asset.')
        stamp = now()
        if active:
            self.db.execute('UPDATE pet_profiles SET is_active=0')
        self.db.execute('''INSERT INTO pet_profiles VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,selected_asset_id=excluded.selected_asset_id,is_active=excluded.is_active,updated_at=excluded.updated_at''', (profile_id, text(name, 'Pet name', 100), asset_id, int(bool(active)), stamp, stamp))
        self.db.execute('INSERT INTO pet_settings VALUES (?,?) ON CONFLICT(profile_id) DO UPDATE SET config=excluded.config', (profile_id, json.dumps(config)))

    def save_profile(self, name, asset_id, config, profile_id=None, active=True):
        with self.db:
            self._write_profile(profile_id or identifier(), name, asset_id, config, active)
            if not self.rows('SELECT id FROM pet_profiles WHERE is_active=1'):
                raise ValueError('Keep one active profile.')
        self.changed()

    def save_position(self, x, y):
        profile = self.active_profile()
        config = dict(profile['config'], x=int(x), y=int(y))
        self.validate_pet(config)
        with self.db:
            self.db.execute('UPDATE pet_settings SET config=? WHERE profile_id=?', (json.dumps(config), profile['id']))

    def get_setting(self, key, default=None):
        row = self.rows('SELECT value FROM app_settings WHERE key=?', (key,))
        return json.loads(row[0]['value']) if row else default

    def app_settings(self):
        settings_dict = {key: self.get_setting(key, value) for key, value in DEFAULT_APP.items()}
        if settings_dict.get('voice_mode') not in ('multilingual', 'google'):
            settings_dict['voice_mode'] = 'google'
        return settings_dict

    @staticmethod
    def validate_settings(config):
        if not isinstance(config, dict):
            raise ValueError('Invalid application settings.')
        if 'voice_hotkey_enabled' not in config:
            config = dict(config, voice_hotkey_enabled=False)
        if 'voice_mode' not in config:
            config = dict(config, voice_mode='google')
        config = dict(config, google_voice_language=config.get('google_voice_language', 'en-IN'),
                      default_music_player=config.get('default_music_player', 'youtube'),
                      spotify_open_mode=config.get('spotify_open_mode', 'auto'))
        if set(config) != set(DEFAULT_APP):
            raise ValueError('Invalid application settings.')
        for key in ('launch_pet', 'start_minimized', 'tray', 'notifications', 'voice_hotkey_enabled'):
            if type(config[key]) is not bool:
                raise ValueError('Invalid setting: ' + key)
        if config['theme'] not in ('light', 'dark') or config['page'] not in ('Dashboard', 'Memory', 'Commands', 'Workflows', 'Pet Studio', 'Activity', 'Settings'):
            raise ValueError('Invalid theme or page.')
        if config.get('voice_mode') not in ('multilingual', 'google'):
            raise ValueError('Invalid voice mode.')
        if config['google_voice_language'] not in ('en-IN', 'ta-IN'):
            raise ValueError('Invalid Google voice language.')
        if config['default_music_player'] not in ('youtube', 'spotify') or config['spotify_open_mode'] not in ('auto', 'browser'):
            raise ValueError('Invalid music player preference.')
        if config['start_minimized'] and not config['tray']:
            raise ValueError('Start minimized requires the system tray.')

    def save_settings(self, config):
        if not isinstance(config, dict):
            raise ValueError('Invalid application settings.')
        if 'voice_hotkey_enabled' not in config:
            config = dict(config, voice_hotkey_enabled=False)
        if 'voice_mode' not in config:
            config = dict(config, voice_mode='google')
        config = dict(config, google_voice_language=config.get('google_voice_language', 'en-IN'),
                      default_music_player=config.get('default_music_player', 'youtube'),
                      spotify_open_mode=config.get('spotify_open_mode', 'auto'))
        self.validate_settings(config)
        with self.db:
            for key, value in config.items():
                self.db.execute('INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))
        self.changed()

    def export_configuration(self):
        return dict(version=1, settings=self.app_settings(), commands=self.commands(), profiles=self.profiles(),
                    registered_applications=[asdict(app) for app in self.list_registered_applications()],
                    file_search=self.file_search_settings(),
                    routines=[{k: r[k] for k in ("id", "command_id", "name", "phrases", "steps", "enabled")} for r in self.workflows.list()])

    def import_configuration(self, payload):
        self.workflows.ensure_idle()
        if not isinstance(payload, dict) or payload.get('version') != 1:
            raise ValueError('Invalid configuration export.')
        settings_payload = dict(payload.get('settings') or {})
        settings_payload.setdefault('voice_hotkey_enabled', False)
        if settings_payload.get('voice_mode') not in ('multilingual', 'google'):
            settings_payload['voice_mode'] = 'google'
        settings_payload.setdefault('google_voice_language', 'en-IN')
        settings_payload.setdefault('default_music_player', 'youtube')
        settings_payload.setdefault('spotify_open_mode', 'auto')
        self.validate_settings(settings_payload)
        search_config = payload.get('file_search', dict(roots=[], everything_executable=''))
        self.validate_file_search_settings(search_config)
        commands, profiles = payload.get('commands'), payload.get('profiles')
        if not isinstance(commands, list) or not isinstance(profiles, list) or len(commands) > 500 or not 1 <= len(profiles) <= 100:
            raise ValueError('Invalid configuration records.')
        if sum(bool(p.get('is_active')) for p in profiles) != 1:
            raise ValueError('Exactly one profile must be active.')
        # Append only; an active imported profile is an explicit switch, existing records survive.
        with self.db:
            registrations = payload.get('registered_applications', [])
            if not isinstance(registrations, list) or len(registrations) > 500:
                raise ValueError('Invalid application registrations.')
            remap = {}
            for registration in registrations:
                self._validate_registration(registration)
                old_id = registration['id']
                if old_id in remap:
                    raise ValueError('Duplicate application registration.')
                new_id, stamp = 'app-' + identifier(), now()
                remap[old_id] = new_id
                status, path = ApplicationValidator.validate_registered_path(registration['executable_path'])
                self.db.execute('INSERT INTO registered_applications VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (new_id, registration['name'], normalize(registration['name']), path, registration.get('publisher'),
                     registration.get('version'), registration.get('icon_path'), registration['source'],
                     int(bool(registration['enabled']) and status == ValidationStatus.VALID),
                     int(status != ValidationStatus.VALID), stamp, stamp))
                self._write_application_aliases(new_id, registration['aliases'])
            routines = payload.get('routines', [])
            if not isinstance(routines, list) or len(routines) > 500:
                raise ValueError('Invalid routine records.')
            routine_commands = {c['id']: c for c in commands if c['action_type'] == 'routine'}
            if len(routine_commands) != len(routines):
                raise ValueError('Routine command links do not match.')
            seen = set()
            for routine in routines:
                if not isinstance(routine, dict) or routine.get('command_id') not in routine_commands or routine.get('id') in seen:
                    raise ValueError('Invalid or duplicate routine link.')
                seen.add(routine['id'])
                command = routine_commands.pop(routine['command_id'])
                if command['target'] != routine['id'] or command['name'] != routine['name'] or command['phrases'] != routine['phrases']:
                    raise ValueError('Routine command metadata does not match.')
                steps = routine['steps']
                self.workflows.validate_steps(steps)
                steps = [dict(step, value=remap.get(step['value'], step['value'])) if step['type'] == 'application' else step for step in steps]
                self.workflows._save(routine['name'], routine['phrases'], steps, False, imported=True)
            for command in commands:
                if command['action_type'] != 'routine':
                    self._write_command(identifier(), command['name'], command['action_type'], remap.get(command['target'], command['target']), command['phrases'], bool(command['enabled']))
            for profile in profiles:
                self._write_profile(identifier(), profile['name'], profile['selected_asset_id'], profile['config'], bool(profile['is_active']))
            for key, value in settings_payload.items():
                self.db.execute('INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))
            self.db.execute('INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', ('file_search', json.dumps(search_config)))
        self.file_session.clear()
        self.file_search = self.create_file_search_service()
        self.changed()

    def backup(self, destination=None):
        path = Path(destination) if destination else self.root / 'backups' / ('petanimal-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + identifier()[:8] + '.db')
        if path.exists():
            raise ValueError('Backup target already exists; choose a new filename.')
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()
        return path

    def restore(self, source):
        self.workflows.ensure_idle()
        source = Path(source).resolve()
        if not source.is_file() or source == self.path.resolve() or source.stat().st_size > 100 * 1024 * 1024:
            raise ValueError('Choose a separate SQLite backup under 100 MB.')
        stored = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
        candidate = sqlite3.connect(':memory:')
        try:
            stored.backup(candidate)
        finally:
            stored.close()
        candidate.row_factory = sqlite3.Row
        try:
            candidate.execute('PRAGMA foreign_keys=ON')
            candidate.execute('PRAGMA trusted_schema=OFF')
            version = candidate.execute('PRAGMA user_version').fetchone()[0]
            if candidate.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or version not in (1, 2, 3, 4, 5, 6, 7) or candidate.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Invalid or incompatible backup.')
            if version == 1:
                candidate.executescript((settings.BASE_DIR / 'src/database/migrations/002_registered_applications.sql').read_text(encoding='utf-8-sig'))
            if version < 3:
                candidate.executescript((settings.BASE_DIR / 'src/database/migrations/003_personal_memory_engine.sql').read_text(encoding='utf-8-sig'))
            if version < 4:
                candidate.executescript((settings.BASE_DIR / 'src/database/migrations/004_simplify_memory.sql').read_text(encoding='utf-8-sig'))
            if version < 5:
                candidate.executescript((settings.BASE_DIR / 'src/database/migrations/005_remove_activity_patterns.sql').read_text(encoding='utf-8-sig'))
            if version < 6:
                candidate.executescript((settings.BASE_DIR / 'src/database/migrations/006_file_open_history.sql').read_text(encoding='utf-8-sig'))
            if version < 7:
                candidate.executescript((settings.BASE_DIR / 'src/database/migrations/007_workflows.sql').read_text(encoding='utf-8-sig'))
            for row in candidate.execute('SELECT path, opened FROM file_open_history'):
                from ..services.file_search import is_local_path
                if not is_local_path(row[0]) or not isinstance(row[1], (float, int)) or not 0 < row[1] < float('inf'):
                    raise ValueError('Invalid file open history.')
            # Require the application's exact schema: no injected triggers/views or altered constraints.
            current_schema = {(r[0], r[1], r[2], r[3]) for r in self.db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            backup_schema = {(r[0], r[1], r[2], r[3]) for r in candidate.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            if current_schema != backup_schema:
                raise ValueError('Backup schema does not match this application.')
            MemoryService.validate_backup(candidate)
            for row in candidate.execute('SELECT * FROM registered_applications').fetchall():
                registration = dict(row)
                registration['aliases'] = [alias[0] for alias in candidate.execute('SELECT alias FROM application_aliases WHERE application_id=?', (row['id'],))]
                self._validate_registration(registration)
                status, _ = ApplicationValidator.validate_registered_path(row['executable_path'])
                if status != ValidationStatus.VALID:
                    candidate.execute('UPDATE registered_applications SET enabled=0,needs_repair=1 WHERE id=?', (row['id'],))
            for row in candidate.execute('SELECT action_type,action_config,enabled FROM commands'):
                target = json.loads(row[1])['target']
                # Removed registrations leave disabled commands for the user to delete/edit.
                if row[0] == 'application' and isinstance(target, str) and re.fullmatch(r'app-[0-9a-f-]{36}', target):
                    if not candidate.execute('SELECT id FROM registered_applications WHERE id=?', (target,)).fetchone():
                        if row[2]:
                            raise ValueError('Command references an unknown application.')
                        continue
                self._validate_command_action(row[0], target, candidate)
            for row in candidate.execute('SELECT r.*,c.action_type,c.action_config FROM routines r JOIN commands c ON c.id=r.command_id'):
                if row['action_type'] != 'routine' or json.loads(row['action_config']) != {'target': row['id']}:
                    raise ValueError('Invalid routine command link.')
                self.workflows.validate_steps(json.loads(row['steps']), connection=candidate)
            if candidate.execute("SELECT count(*) FROM commands c WHERE c.action_type='routine' AND NOT EXISTS(SELECT 1 FROM routines r WHERE r.command_id=c.id)").fetchone()[0]:
                raise ValueError('Unlinked routine command.')
            for row in candidate.execute('SELECT config FROM pet_settings'):
                self.validate_pet(json.loads(row[0]))
            if candidate.execute('SELECT count(*) FROM pet_profiles WHERE is_active=1').fetchone()[0] != 1:
                raise ValueError('Backup must have one active profile.')
            for row in candidate.execute('SELECT id,filename,imported FROM pet_assets'):
                root = self.root / 'pets/imported' if row['imported'] else settings.PET_IMAGE_DIR
                asset = (root / row['filename']).resolve()
                if asset.parent != root.resolve() or asset.suffix.lower() != '.png' or not asset.is_file():
                    raise ValueError('A backup pet asset is missing or invalid. Keep the pets folder with your backup.')
            imported_settings = dict(DEFAULT_APP)
            for row in candidate.execute('SELECT key,value FROM app_settings'):
                if row[0] in imported_settings:
                    imported_settings[row[0]] = json.loads(row[1])
                elif row[0] == 'file_search':
                    self.validate_file_search_settings(json.loads(row[1]))
            if imported_settings.get('voice_mode') not in ('multilingual', 'google'):
                imported_settings['voice_mode'] = 'google'
            self.validate_settings(imported_settings)
            for row in candidate.execute('SELECT m.memory_value FROM memories m JOIN memory_categories c ON c.id=m.category_id WHERE c.sensitive=1'):
                secrets.decrypt(row[0])
            # A backup must never resume its former runtime's temporary session.
            candidate.execute("DELETE FROM memories WHERE lifetime='session'")
            self.backup()  # Recovery snapshot before replacing the live database.
            candidate.commit()
            candidate.backup(self.db)
            with self.db:
                self._seed_spotify()
            self.workflows.recover_interrupted()
            self.memory_service.cleanup_session(startup=True)
            self.file_session.clear()
            self.file_search = self.create_file_search_service()
            self._memory_confirmations.clear()
            self.memory_conversation.clear()
        finally:
            candidate.close()
        self.changed()

    @staticmethod
    def _validate_registration(record):
        if not isinstance(record, dict) or not re.fullmatch(r'app-[0-9a-f-]{36}', record.get('id', '')):
            raise ValueError('Invalid registered application ID.')
        text(record.get('name'), 'Application name', 150)
        if record.get('enabled') not in (0, 1) or record.get('needs_repair') not in (0, 1):
            raise ValueError('Invalid application status.')
        try:
            for source in record['source'].split(','):
                DiscoverySource(source)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValueError('Invalid discovery source.') from None
        status, _ = ApplicationValidator.validate_registered_path(record.get('executable_path'))
        if status not in (ValidationStatus.VALID, ValidationStatus.MISSING_EXECUTABLE):
            raise ValueError('Unsafe registered executable in backup.')
        aliases = record.get('aliases')
        if not isinstance(aliases, (list, tuple)) or not 1 <= len(aliases) <= 30:
            raise ValueError('Invalid application aliases.')
        for alias in aliases:
            text(alias, 'Alias', 150)
            if not normalize_input(alias).valid:
                raise ValueError('Invalid application alias.')
