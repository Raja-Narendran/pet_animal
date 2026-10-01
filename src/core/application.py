"""Single application core shared by both windows; no UI or HTTP dependency."""
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from . import secrets
from ..config.settings import settings
from ..services.windows_launcher import WindowsLauncher


def identifier():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize(text):
    return ' '.join(text.casefold().split())


def text(value, label, limit=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise ValueError(f'{label} must contain 1–{limit} characters.')
    return value.strip()


DEFAULT_PET = dict(size=240, x=None, y=None, always_on_top=True, animations=True,
                   chat_width=320, text_size=13, background='#18181b', radius=20, opacity=0.94)
DEFAULT_APP = dict(launch_pet=True, start_minimized=False, tray=True, notifications=True, theme='light', page='Dashboard', voice_mode='english')


class ApplicationCore:
    def __init__(self, data_dir, launcher=None):
        self.root = Path(data_dir)
        for folder in ('database', 'pets/imported', 'backups', 'logs'):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'database/petanimal.db'
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA trusted_schema=OFF')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.launcher = launcher or WindowsLauncher()
        self.listeners = []
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            raise ValueError('This database requires a newer Pet Animal version.')
        if version == 0:
            migration = settings.BASE_DIR / 'src/database/migrations/001_initial.sql'
            self.db.executescript('BEGIN;\n' + migration.read_text(encoding='utf-8-sig') + '\nCOMMIT;')
        self._seed()

    def close(self):
        self.db.close()

    def changed(self):
        for callback in tuple(self.listeners):
            callback()

    def rows(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args)]

    def _seed(self):
        with self.db:
            for name, sensitive in [('Personal Information', 0), ('Passwords and Credit and debit card details', 1), ('Important Notes', 0), ('Custom', 0)]:
                self.db.execute('INSERT OR IGNORE INTO memory_categories VALUES (?,?,?)', (identifier(), name, sensitive))
            for state, filename in settings.PET_STATES.items():
                self.db.execute('INSERT OR IGNORE INTO pet_assets VALUES (?,?,?,0)', ('builtin-' + state, 'Husky · ' + state.title(), filename))
            if not self.rows('SELECT id FROM pet_profiles'):
                self._write_profile(identifier(), 'Husky', 'builtin-idle', DEFAULT_PET, True)
            if not self.rows('SELECT id FROM commands') and not self.get_setting('commands_seeded', False):
                for key in sorted(WindowsLauncher.SUPPORTED_APPS):
                    self._write_command(identifier(), 'Open ' + key.title(), 'application', key, ['open ' + key, 'launch ' + key, 'start ' + key, key], True, True)
                for key, url in settings.SUPPORTED_URLS.items():
                    self._write_command(identifier(), 'Open ' + key.title(), 'url', url, ['open ' + key, key], True, True)
                self.db.execute('INSERT INTO app_settings VALUES (?,?)', ('commands_seeded', 'true'))

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

    def memories(self, query='', category_id=None):
        # Sensitive values are never decrypted by a listing/search operation.
        args = [f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%']
        sql = '''SELECT m.*, c.name AS category, c.sensitive FROM memories m JOIN memory_categories c ON c.id=m.category_id
                 WHERE (m.title LIKE ? OR m.memory_key LIKE ? OR m.description LIKE ? OR (c.sensitive=0 AND m.memory_value LIKE ?))'''
        if category_id:
            sql += ' AND m.category_id=?'
            args.append(category_id)
        result = self.rows(sql + ' ORDER BY m.updated_at DESC', args)
        for row in result:
            if row['sensitive']:
                row['memory_value'] = '••••••••'
        return result

    def get_memory(self, memory_id, reveal=False):
        rows = self.rows('SELECT m.*, c.sensitive FROM memories m JOIN memory_categories c ON c.id=m.category_id WHERE m.id=?', (memory_id,))
        if not rows:
            return None
        row = rows[0]
        if row['sensitive']:
            row['memory_value'] = secrets.decrypt(row['memory_value']) if reveal else '••••••••'
        return row

    def get_memory_by_key(self, key):
        rows = self.rows('SELECT id FROM memories WHERE memory_key=? AND enabled=1', (key,))
        return self.get_memory(rows[0]['id']) if rows else None

    def save_memory(self, category_id, title, key, value, description='', enabled=True, memory_id=None):
        category = self._category(category_id)
        title, key, value = text(title, 'Title', 150), text(key, 'Key', 200), text(value, 'Value', 20000)
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError('Description is too long.')
        if category['sensitive']:
            value = secrets.encrypt(value)
        memory_id = memory_id or identifier()
        stamp = now()
        with self.db:
            self.db.execute('''INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                category_id=excluded.category_id,title=excluded.title,memory_key=excluded.memory_key,memory_value=excluded.memory_value,
                description=excluded.description,enabled=excluded.enabled,updated_at=excluded.updated_at''',
                (memory_id, category_id, title, key, value, description, int(bool(enabled)), stamp, stamp))
        self.changed()
        return memory_id

    def delete_memory(self, memory_id):
        with self.db:
            self.db.execute('DELETE FROM memories WHERE id=?', (memory_id,))
        self.changed()

    def export_memories(self):
        result = self.rows('''SELECT m.title,m.memory_key,m.memory_value,m.description,m.enabled,c.name AS category
                    FROM memories m JOIN memory_categories c ON m.category_id=c.id WHERE c.sensitive=0''')
        return dict(version=1, memories=result)

    def import_memories(self, payload):
        if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('memories'), list) or len(payload['memories']) > 10000:
            raise ValueError('Invalid memory export.')
        prepared = []
        keys = set()
        for record in payload['memories']:
            if not isinstance(record, dict):
                raise ValueError('Invalid memory record.')
            key = text(record.get('memory_key'), 'Key', 200)
            if key in keys or self.rows('SELECT id FROM memories WHERE memory_key=?', (key,)):
                raise ValueError(f'Memory key already exists: {key}. Import does not overwrite data.')
            keys.add(key)
            category = text(record.get('category'), 'Category', 100)
            existing = self.rows('SELECT sensitive FROM memory_categories WHERE name=?', (category,))
            if existing and existing[0]['sensitive']:
                raise ValueError('Sensitive categories cannot be imported from plain JSON.')
            description = record.get('description', '')
            if not isinstance(description, str) or len(description) > 4000 or record.get('enabled', 1) not in (0, 1):
                raise ValueError('Invalid memory properties.')
            prepared.append((category, text(record.get('title'), 'Title', 150), key, text(record.get('memory_value'), 'Value', 20000), description, record.get('enabled', 1)))
        with self.db:
            for category, title, key, value, description, enabled in prepared:
                self.db.execute('INSERT OR IGNORE INTO memory_categories VALUES (?,?,0)', (identifier(), category))
                category_id = self.rows('SELECT id FROM memory_categories WHERE name=?', (category,))[0]['id']
                self.db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)', (identifier(), category_id, title, key, value, description, enabled, now(), now()))
        self.changed()

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

    def _write_command(self, command_id, name, action, target, phrases, enabled=True, builtin=False):
        name = text(name, 'Command name', 150)
        self.validate_action(action, target)
        if not isinstance(phrases, list) or not 1 <= len(phrases) <= 30:
            raise ValueError('Enter 1–30 phrases.')
        normalized = [normalize(text(p, 'Phrase', 200)) for p in phrases]
        if len(set(normalized)) != len(normalized):
            raise ValueError('Duplicate phrases in this command.')
        if any(p in ('help', 'what is my name') or p.startswith('remember my name as ') for p in normalized):
            raise ValueError('This phrase is reserved for memory or help.')
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
        with self.db:
            self._write_command(command_id or identifier(), name, action, target, phrases, enabled)
        self.changed()

    def delete_command(self, command_id):
        with self.db:
            self.db.execute('DELETE FROM commands WHERE id=?', (command_id,))
        self.changed()

    def propose_memory(self, value):
        return text(value, 'Name', 150)

    def confirm_name(self, value):
        category = self.rows("SELECT id FROM memory_categories WHERE name='Personal Information'")[0]['id']
        rows = self.rows('SELECT id FROM memories WHERE memory_key=?', ('user.name',))
        existing = rows[0] if rows else None
        return self.save_memory(category, 'My name', 'user.name', self.propose_memory(value), memory_id=existing['id'] if existing else None)

    def resolve_voice_phrase(self, phrase):
        """Explicit spoken aliases only; exact registered/disabled phrases take precedence."""
        if not isinstance(phrase, str) or len(phrase) > 500:
            return phrase
        normalized = normalize(phrase)
        if self.rows('SELECT id FROM command_phrases WHERE normalized_phrase=?', (normalized,)):
            return phrase
        from ..commands.voice_phrases import normalize_mixed_voice
        translated = normalize_mixed_voice(phrase)
        # A canonical registered phrase also wins, especially when disabled.
        if self.rows('SELECT id FROM command_phrases WHERE normalized_phrase=?', (normalize(translated),)):
            return translated
        normalized = normalize(translated)
        aliases = {'google chrome': ('application', 'chrome'), 'chrome': ('application', 'chrome'),
                   'note pad': ('application', 'notepad'), 'notepad': ('application', 'notepad'),
                   'calculator': ('application', 'calculator'), 'calc': ('application', 'calculator'),
                   'file explorer': ('application', 'explorer'), 'windows explorer': ('application', 'explorer'),
                   'explorer': ('application', 'explorer'), 'vs code': ('application', 'vscode'),
                   'visual studio code': ('application', 'vscode'), 'vscode': ('application', 'vscode'),
                   'you tube': ('url', 'https://www.youtube.com'), 'youtube': ('url', 'https://www.youtube.com'),
                   'google': ('url', 'https://www.google.com')}
        candidate = re.sub(r'^(open|launch|start|run) (the )?', '', normalized)
        action_target = aliases.get(candidate)
        if action_target:
            matches = [c for c in self.commands() if c['enabled'] and (c['action_type'], c['target']) == action_target]
            if len(matches) == 1:
                return matches[0]['phrases'][0]
        return translated

    def execute(self, phrase, defer_browser=False):
        if not isinstance(phrase, str) or len(phrase) > 500:
            return dict(success=False, message='Command is too long.', pet_state='error')
        normalized = normalize(phrase)
        if normalized == 'what is my name':
            memory = self.get_memory_by_key('user.name')
            return dict(success=bool(memory), message=memory['memory_value'] if memory else 'Your name has not been saved.', pet_state='success' if memory else 'idle')
        match = re.fullmatch(r'remember\s+my\s+name\s+as\s+(.+)', phrase.strip(), re.IGNORECASE)
        if match:
            try:
                value = self.propose_memory(match[1])
                return dict(success=False, message=f'Save your name as {value}?', confirmation=value, pet_state='thinking')
            except ValueError as error:
                return dict(success=False, message=str(error), pet_state='error')
        if normalized == 'help':
            names = [c['phrases'][0] for c in self.commands() if c['enabled']]
            return dict(success=True, message='Commands: ' + ', '.join(names) + '\nBrowser: search <query>; play <song> on youtube\nMemory: remember my name as <name>; what is my name', pet_state='idle')
        found = self.rows('''SELECT c.* FROM commands c JOIN command_phrases p ON p.command_id=c.id
                            WHERE p.normalized_phrase=? AND c.enabled=1''', (normalized,))
        command_id = None
        # Registered phrases (including disabled ones) take precedence.
        registered = self.rows('SELECT id FROM command_phrases WHERE normalized_phrase=?', (normalized,))
        if not registered:
            match = re.fullmatch(r'(search for|search on google|search google for|search google|search|look up|find|google) (.+)', normalized)
            action = 'search'
            if not match:
                match = re.fullmatch(r'(play on youtube|youtube play|play song|play music|play) (.+)', normalized)
                action = 'music'
            if match:
                target = match[2]
                if action == 'music' and target.endswith(' on youtube'):
                    target = target[:-11].strip()
                if target and not any(ord(c) < 32 for c in phrase):
                    if defer_browser:
                        return dict(success=True, message='Searching…' if action == 'search' else 'Finding your song…',
                                    pet_state='working', browser_action=action, browser_target=target)
                    try:
                        handler = self.launcher.search_web if action == 'search' else self.launcher.play_youtube
                        success, message = handler(target)
                    except Exception:
                        success, message = False, 'The browser action could not be executed.'
                    return self.finish_browser_action(action, success, message)
        if not found:
            success, message = False, 'Unsupported command. Type help to see registered phrases.'
        else:
            record = found[0]
            command_id = record['id']
            try:
                target = json.loads(record['action_config'])['target']
                self.validate_action(record['action_type'], target)
                if record['action_type'] == 'application':
                    success, message = self.launcher.open_application(target)
                else:
                    success, message = self.launcher.open_registered_url(target)
            except Exception:
                success, message = False, 'The configured action could not be executed.'
        # Unsupported input and memory contents never enter history/logs.
        with self.db:
            self.db.execute('INSERT INTO command_history VALUES (?,?,?,?,?,?)', (identifier(), command_id, normalized if found else '[unsupported command]', 'success' if success else 'failed', '' if success else message, now()))
        self.changed()
        return dict(success=success, message=message, pet_state='success' if success else 'error')

    def finish_browser_action(self, action, success, message):
        # Keep free-form searches and song titles out of persistent history.
        with self.db:
            self.db.execute('INSERT INTO command_history VALUES (?,?,?,?,?,?)',
                            (identifier(), None, '[web search]' if action == 'search' else '[music playback]',
                             'success' if success else 'failed', '' if success else 'Browser action failed.', now()))
        self.changed()
        return dict(success=success, message=message, pet_state='success' if success else 'error')

    def history(self, status='', date='', command_id=None):
        sql = '''SELECT h.*, COALESCE(c.name, CASE h.trigger_phrase WHEN '[web search]' THEN 'Web search' WHEN '[music playback]' THEN 'Music playback' ELSE 'Unsupported / deleted command' END) AS name FROM command_history h LEFT JOIN commands c ON c.id=h.command_id WHERE 1=1'''
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
        with self.db:
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
        return {key: self.get_setting(key, value) for key, value in DEFAULT_APP.items()}

    @staticmethod
    def validate_settings(config):
        if not isinstance(config, dict):
            raise ValueError('Invalid application settings.')
        if 'voice_mode' not in config:
            config = dict(config, voice_mode='english')
        if set(config) != set(DEFAULT_APP):
            raise ValueError('Invalid application settings.')
        for key in ('launch_pet', 'start_minimized', 'tray', 'notifications'):
            if type(config[key]) is not bool:
                raise ValueError('Invalid setting: ' + key)
        if config['theme'] not in ('light', 'dark') or config['page'] not in ('Dashboard', 'Memory', 'Commands', 'Pet Studio', 'Activity', 'Settings'):
            raise ValueError('Invalid theme or page.')
        if config.get('voice_mode') not in ('english', 'multilingual'):
            raise ValueError('Invalid voice mode.')
        if config['start_minimized'] and not config['tray']:
            raise ValueError('Start minimized requires the system tray.')

    def save_settings(self, config):
        if not isinstance(config, dict):
            raise ValueError('Invalid application settings.')
        if 'voice_mode' not in config:
            config = dict(config, voice_mode='english')
        self.validate_settings(config)
        with self.db:
            for key, value in config.items():
                self.db.execute('INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))
        self.changed()

    def export_configuration(self):
        return dict(version=1, settings=self.app_settings(), commands=self.commands(), profiles=self.profiles())

    def import_configuration(self, payload):
        if not isinstance(payload, dict) or payload.get('version') != 1:
            raise ValueError('Invalid configuration export.')
        settings_payload = dict(payload.get('settings') or {})
        if 'voice_mode' not in settings_payload:
            settings_payload['voice_mode'] = 'english'
        self.validate_settings(settings_payload)
        commands, profiles = payload.get('commands'), payload.get('profiles')
        if not isinstance(commands, list) or not isinstance(profiles, list) or len(commands) > 500 or not 1 <= len(profiles) <= 100:
            raise ValueError('Invalid configuration records.')
        if sum(bool(p.get('is_active')) for p in profiles) != 1:
            raise ValueError('Exactly one profile must be active.')
        # Append only; an active imported profile is an explicit switch, existing records survive.
        with self.db:
            for command in commands:
                self._write_command(identifier(), command['name'], command['action_type'], command['target'], command['phrases'], bool(command['enabled']))
            for profile in profiles:
                self._write_profile(identifier(), profile['name'], profile['selected_asset_id'], profile['config'], bool(profile['is_active']))
            for key, value in payload['settings'].items():
                self.db.execute('INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))
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
        source = Path(source).resolve()
        if not source.is_file() or source == self.path.resolve() or source.stat().st_size > 100 * 1024 * 1024:
            raise ValueError('Choose a separate SQLite backup under 100 MB.')
        candidate = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
        candidate.row_factory = sqlite3.Row
        try:
            candidate.execute('PRAGMA trusted_schema=OFF')
            if candidate.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or candidate.execute('PRAGMA user_version').fetchone()[0] != 1 or candidate.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Invalid or incompatible backup.')
            # Require the application's exact schema: no injected triggers/views or altered constraints.
            current_schema = {(r[0], r[1], r[2], r[3]) for r in self.db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            backup_schema = {(r[0], r[1], r[2], r[3]) for r in candidate.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            if current_schema != backup_schema:
                raise ValueError('Backup schema does not match this application.')
            for row in candidate.execute('SELECT action_type,action_config FROM commands'):
                self.validate_action(row[0], json.loads(row[1])['target'])
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
            self.validate_settings(imported_settings)
            for row in candidate.execute('SELECT m.memory_value FROM memories m JOIN memory_categories c ON c.id=m.category_id WHERE c.sensitive=1'):
                secrets.decrypt(row[0])
            self.backup()  # Recovery snapshot before replacing the live database.
            candidate.backup(self.db)
        finally:
            candidate.close()
        self.changed()
