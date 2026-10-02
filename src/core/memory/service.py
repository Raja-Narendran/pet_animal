"""SQLite-backed memory business rules. No GUI, model, network, or OS actions."""
import math
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from .. import secrets
from .models import (DEFAULT_IMPORTANCE, MemoryConflict, MemoryConflictType,
                     MemoryLifetime, MemoryScope, MemorySource, MemoryType, MemoryQuery)

MASK = '••••••••'
SELECT_MEMORY = '''SELECT m.*,c.name AS category,c.sensitive FROM memories m
                   JOIN memory_categories c ON c.id=m.category_id'''
STANDARD_ALIASES = {
    'user.name': ('my name', 'name', 'user name'),
    'preferred.browser': ('my browser', 'default browser', 'preferred browser'),
    'preferred.editor': ('my editor', 'my code editor', 'preferred editor', 'default editor', 'preferred.code_editor'),
}


def normalize(value):
    return ' '.join(value.casefold().split())


def checked_text(value, label, limit, empty=False):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError(f'Invalid {label.lower()}.')
    value = value.strip()
    if not empty and not value:
        raise ValueError(f'{label} cannot be empty.')
    return value


def timestamp(value, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('Invalid memory timestamp.')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        raise ValueError('Memory timestamps must include a timezone.') from None


def score_value(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'{label} must be between 0 and 1.')
    return float(value)


def labels(values, label, limit=100):
    if not isinstance(values, (list, tuple)) or len(values) > 30:
        raise ValueError(f'{label} must contain at most 30 entries.')
    result = []
    for value in values:
        value = normalize(checked_text(value, label, limit))
        if any(ord(c) < 32 for c in value):
            raise ValueError(f'Invalid {label.lower()}.')
        if value not in result:
            result.append(value)
    return result


class MemoryService:
    """Owns the existing memories table and its metadata/graph child tables."""
    def __init__(self, db, changed=None, session_id=None, clock=None):
        self.db = db
        self.db.row_factory = sqlite3.Row
        self.changed = changed or (lambda: None)
        self.session_id = session_id or str(uuid.uuid4())
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.profile_id = 'default'
        self.cleanup_session(startup=True, notify=False)
        self.expire_memories(delete=True, notify=False)
        from .retrieval import MemoryRetriever
        self.retriever = MemoryRetriever(self)

    def now(self):
        value = self.clock()
        if isinstance(value, str):
            return timestamp(value)
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError('The memory clock must return a timezone-aware datetime.')
        return value.astimezone(timezone.utc).isoformat()

    def _rows(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args)]

    def _category(self, category_id):
        row = self.db.execute('SELECT * FROM memory_categories WHERE id=?', (category_id,)).fetchone()
        if row is None:
            raise ValueError('Choose an existing category.')
        return dict(row)

    def _raw(self, memory_id):
        row = self.db.execute(SELECT_MEMORY + ' WHERE m.id=?', (memory_id,)).fetchone()
        return dict(row) if row else None

    def _decorate(self, row, reveal=False):
        row = dict(row)
        if row['sensitive']:
            row['memory_value'] = secrets.decrypt(row['memory_value']) if reveal else MASK
        row['tags'] = [r[0] for r in self.db.execute('SELECT tag FROM memory_tags WHERE memory_id=? ORDER BY tag', (row['id'],))]
        row['aliases'] = [r[0] for r in self.db.execute('SELECT alias FROM memory_aliases WHERE memory_id=? ORDER BY normalized_alias', (row['id'],))]
        row['expired'] = bool(row['expires_at'] and row['expires_at'] <= self.now())
        return row

    def get_memory(self, memory_id, reveal=False):
        row = self._raw(memory_id)
        return self._decorate(row, reveal) if row else None

    def find_existing(self, key, reveal=False):
        key = normalize(checked_text(key, 'Key', 200))
        row = self.db.execute(SELECT_MEMORY + ' WHERE lower(m.memory_key)=?', (key,)).fetchone()
        if row is None:
            row = self.db.execute(SELECT_MEMORY + ' WHERE lower(m.title)=?', (key,)).fetchone()
        if row is None and key.startswith(('my ', 'the ')):
            stripped = key.partition(' ')[2].strip()
            row = self.db.execute(SELECT_MEMORY + ' WHERE lower(m.title)=? OR lower(m.memory_key)=?', (stripped, stripped)).fetchone()
            if row is None:
                slug = re.sub(r'[^a-z0-9_.]+', '.', stripped).strip('.')
                if slug:
                    row = self.db.execute(SELECT_MEMORY + ' WHERE lower(m.memory_key)=?', (slug,)).fetchone()
        if row is None:
            slug = re.sub(r'[^a-z0-9_.]+', '.', key).strip('.')
            if slug:
                row = self.db.execute(SELECT_MEMORY + ' WHERE lower(m.memory_key)=?', (slug,)).fetchone()
        if row is None:
            row = self.db.execute(SELECT_MEMORY + ''' JOIN memory_aliases a ON a.memory_id=m.id
                               WHERE a.normalized_alias=?''', (key,)).fetchone()
        return self._decorate(row, reveal=reveal) if row else None

    def active_pet_profile(self):
        row = self.db.execute('SELECT id FROM pet_profiles WHERE is_active=1').fetchone()
        return row[0] if row else None

    def applicable(self, row):
        if not row['enabled'] or (row['expires_at'] and row['expires_at'] <= self.now()):
            return False
        if row['lifetime'] == MemoryLifetime.SESSION.value and row['session_id'] != self.session_id:
            return False
        scope = row['memory_scope']
        if scope == MemoryScope.PROFILE.value:
            return row['scope_id'] == self.profile_id
        if scope == MemoryScope.PET_PROFILE.value:
            return row['scope_id'] == self.active_pet_profile()
        if scope == MemoryScope.SESSION.value:
            return row['session_id'] == self.session_id
        return True

    def list_memories(self, query='', category_id=None, memory_type=None, memory_scope=None,
                      enabled=None, sensitive=None, include_expired=True, include_system=False, sort='updated', expired=None):
        query = normalize(checked_text(query, 'Search', 1000, empty=True))
        if memory_type is not None:
            memory_type = MemoryType(memory_type).value
        if memory_scope is not None:
            memory_scope = MemoryScope(memory_scope).value
        rows = []
        for raw in self._rows(SELECT_MEMORY):
            if category_id and raw['category_id'] != category_id:
                continue
            if memory_type and raw['memory_type'] != memory_type:
                continue
            if memory_scope and raw['memory_scope'] != memory_scope:
                continue
            if enabled is not None and bool(raw['enabled']) != bool(enabled):
                continue
            if sensitive is not None and bool(raw['sensitive']) != bool(sensitive):
                continue
            if not include_system and raw['memory_type'] == MemoryType.SYSTEM.value:
                continue
            row = self._decorate(raw)
            if not include_expired and row['expired']:
                continue
            if expired is not None and row['expired'] != bool(expired):
                continue
            searchable = [row['title'], row['memory_key'], row['description'], *row['tags'], *row['aliases']]
            if not row['sensitive']:
                searchable.append(row['memory_value'])
            if query and not any(query in normalize(v) for v in searchable):
                continue
            rows.append(row)
        if sort == 'updated':
            order = lambda r: (r['updated_at'], r['id'])
        elif sort == 'recently_used':
            order = lambda r: (r['last_accessed_at'] or '', r['id'])
        elif sort == 'most_used':
            order = lambda r: (r['access_count'], r['last_accessed_at'] or '', r['id'])
        else:
            raise ValueError('Unknown memory sort.')
        return sorted(rows, key=order, reverse=True)

    def _prepare(self, category_id, title, key, value, description='', enabled=True,
                 memory_type=MemoryType.KNOWLEDGE, memory_scope=None, lifetime=None,
                 importance=None, confidence=1.0, source=MemorySource.USER_MANUAL,
                 expires_at=None, tags=(), aliases=(), scope_id=None, session_id=None):
        category = self._category(category_id)
        key = normalize(checked_text(key, 'Key', 200))
        key = next((canonical for canonical, values in STANDARD_ALIASES.items() if key in values), key)
        if any(ord(c) < 32 for c in key):
            raise ValueError('Invalid memory key.')
        kind = MemoryType(memory_type)
        if memory_scope is None:
            memory_scope = MemoryScope.SESSION if kind == MemoryType.CONTEXT else MemoryScope.GLOBAL
        scope = MemoryScope(memory_scope)
        if lifetime is None:
            lifetime = (MemoryLifetime.SESSION if scope == MemoryScope.SESSION else
                        MemoryLifetime.TEMPORARY if scope == MemoryScope.TEMPORARY or expires_at else
                        MemoryLifetime.PERSISTENT)
        life = MemoryLifetime(lifetime)
        if life == MemoryLifetime.SESSION and scope == MemoryScope.GLOBAL:
            scope = MemoryScope.SESSION
        elif life == MemoryLifetime.TEMPORARY and scope == MemoryScope.GLOBAL:
            scope = MemoryScope.TEMPORARY
        if scope == MemoryScope.SESSION and life != MemoryLifetime.SESSION:
            raise ValueError('Session scope requires session lifetime.')
        if scope == MemoryScope.TEMPORARY and life != MemoryLifetime.TEMPORARY:
            raise ValueError('Temporary scope requires temporary lifetime.')
        if kind == MemoryType.CONTEXT and life == MemoryLifetime.PERSISTENT:
            raise ValueError('Context memories require a session or temporary lifetime.')
        expires_at = timestamp(expires_at, optional=True)
        if life == MemoryLifetime.TEMPORARY and expires_at is None:
            expires_at = (datetime.fromisoformat(self.now()) + timedelta(minutes=5)).isoformat()
        if scope == MemoryScope.PROFILE:
            scope_id = scope_id or self.profile_id
        elif scope == MemoryScope.PET_PROFILE:
            scope_id = scope_id or self.active_pet_profile()
            if not self.db.execute('SELECT id FROM pet_profiles WHERE id=?', (scope_id,)).fetchone():
                raise ValueError('Choose an existing pet profile for this memory.')
        else:
            if scope_id is not None:
                raise ValueError('This scope cannot have a profile owner.')
        if scope_id is not None:
            scope_id = checked_text(scope_id, 'Scope owner', 100)
        if enabled not in (0, 1) or not isinstance(enabled, (int, bool)):
            raise ValueError('Invalid memory enabled flag.')
        return dict(category_id=category_id, title=checked_text(title, 'Title', 150), memory_key=key,
                    memory_value=checked_text(value, 'Value', 20000), description=checked_text(description, 'Description', 4000, empty=True),
                    enabled=int(enabled), memory_type=kind.value, memory_scope=scope.value, lifetime=life.value,
                    importance=score_value(DEFAULT_IMPORTANCE[kind] if importance is None else importance, 'Importance'),
                    confidence=score_value(0.0 if confidence is None else confidence, 'Confidence'), source=MemorySource(source).value,
                    expires_at=expires_at, scope_id=scope_id,
                    session_id=self.session_id if life == MemoryLifetime.SESSION else None,
                    tags=labels(tags, 'Tags'), aliases=labels(aliases, 'Aliases', 150), sensitive=category['sensitive'])

    def _check_labels(self, memory_id, key, aliases):
        for alias in aliases:
            owner = self.db.execute('SELECT memory_id FROM memory_aliases WHERE normalized_alias=?', (alias,)).fetchone()
            key_owner = self.db.execute('SELECT id FROM memories WHERE lower(memory_key)=?', (alias,)).fetchone()
            if (owner and owner[0] != memory_id) or (key_owner and key_owner[0] != memory_id):
                raise ValueError('A memory alias already belongs to another memory.')
        alias_owner = self.db.execute('SELECT memory_id FROM memory_aliases WHERE normalized_alias=?', (key,)).fetchone()
        if alias_owner and alias_owner[0] != memory_id:
            raise ValueError('This key is an alias of another memory.')

    def _write_labels(self, memory_id, tags, aliases):
        self.db.execute('DELETE FROM memory_tags WHERE memory_id=?', (memory_id,))
        self.db.execute('DELETE FROM memory_aliases WHERE memory_id=?', (memory_id,))
        for tag in tags:
            self.db.execute('INSERT INTO memory_tags VALUES (?,?,?)', (str(uuid.uuid4()), memory_id, tag))
        for alias in aliases:
            self.db.execute('INSERT INTO memory_aliases VALUES (?,?,?,?)', (str(uuid.uuid4()), memory_id, alias, alias))

    def _create(self, data, memory_id=None):
        memory_id = memory_id or str(uuid.uuid4())
        self._check_labels(memory_id, data['memory_key'], data['aliases'])
        stamp = self.now()
        fields = {k: v for k, v in data.items() if k not in ('tags', 'aliases', 'sensitive')}
        if data['sensitive']:
            fields['memory_value'] = secrets.encrypt(fields['memory_value'])
        fields.update(id=memory_id, created_at=stamp, updated_at=stamp)
        columns = ','.join(fields)
        self.db.execute(f'INSERT INTO memories({columns}) VALUES ({",".join("?" for _ in fields)})', tuple(fields.values()))
        self._write_labels(memory_id, data['tags'], data['aliases'])
        return memory_id

    def create_memory(self, category_id, title, key, value, description='', enabled=True, confirmed=False, **metadata):
        kind_key = normalize(checked_text(key, 'Key', 200))
        canonical = next((canonical for canonical, values in STANDARD_ALIASES.items() if kind_key in values), kind_key)
        if 'memory_type' not in metadata:
            if canonical.startswith('user.'):
                metadata['memory_type'] = MemoryType.PROFILE
            elif canonical.startswith('preferred.'):
                metadata['memory_type'] = MemoryType.PREFERENCE
        data = self._prepare(category_id, title, key, value, description, enabled, **metadata)
        existing = self.find_existing(data['memory_key'])
        if existing:
            if not existing['sensitive'] and existing['memory_value'] == data['memory_value'] and existing['memory_type'] == data['memory_type'] and existing['memory_scope'] == data['memory_scope'] and existing['scope_id'] == data['scope_id'] and existing['lifetime'] == data['lifetime']:
                return existing['id']
            if confirmed:
                return self.update_memory(existing['id'], confirmed=True, category_id=category_id, title=title,
                                          value=value, description=description, enabled=enabled, **metadata)
            self._raise_conflict(existing, data, value_changed=True)
        if 'aliases' not in metadata:
            data['aliases'] = list(STANDARD_ALIASES.get(data['memory_key'], ()))
        with self.db:
            memory_id = self._create(data)
        self.changed()
        return memory_id

    def _raise_conflict(self, existing, data, value_changed=False):
        if existing['memory_type'] != data['memory_type']:
            kind = MemoryConflictType.TYPE_CONFLICT
        elif existing['memory_scope'] != data['memory_scope'] or existing['scope_id'] != data['scope_id'] or existing['lifetime'] != data['lifetime']:
            kind = MemoryConflictType.SCOPE_CONFLICT
        elif value_changed:
            kind = MemoryConflictType.VALUE_CHANGE
        else:
            return
        raise MemoryConflict(kind, existing)

    def update_memory(self, memory_id, confirmed=False, **changes):
        existing = self.get_memory(memory_id)
        if existing is None:
            raise ValueError('Memory no longer exists.')
        allowed = {'category_id','title','key','value','description','enabled','memory_type','memory_scope',
                   'lifetime','importance','confidence','source','expires_at','tags','aliases','scope_id'}
        if set(changes) - allowed:
            raise ValueError('Unknown memory properties.')
        base = {k: existing[k] for k in allowed if k in existing}
        base.update(key=existing['memory_key'], value=existing['memory_value'])
        base.update(changes)
        if 'source' not in changes and set(changes) - {'enabled'}:
            base['source'] = MemorySource.USER_MANUAL.value
        if 'category_id' in changes and changes['category_id'] != existing['category_id'] and 'value' not in changes:
            if existing['sensitive'] or self._category(changes['category_id'])['sensitive']:
                raise ValueError('Re-enter the value when moving a memory to or from a sensitive category.')
        if 'memory_scope' in changes and 'scope_id' not in changes:
            base['scope_id'] = None
        if 'memory_scope' in changes and 'lifetime' not in changes:
            base['lifetime'] = None
        data = self._prepare(**base)
        value_changed = 'value' in changes and (existing['sensitive'] or changes['value'].strip() != existing['memory_value'])
        if not confirmed:
            self._raise_conflict(existing, data, value_changed)
        owner = self.find_existing(data['memory_key'])
        if owner and owner['id'] != memory_id:
            raise MemoryConflict(MemoryConflictType.DUPLICATE, owner)
        self._check_labels(memory_id, data['memory_key'], data['aliases'])
        fields = {k: v for k, v in data.items() if k not in ('tags', 'aliases', 'sensitive')}
        if existing['sensitive'] and 'value' not in changes:
            fields['memory_value'] = self._raw(memory_id)['memory_value']
        elif data['sensitive']:
            fields['memory_value'] = secrets.encrypt(data['memory_value'])
        fields['updated_at'] = self.now()
        with self.db:
            self.db.execute(f'UPDATE memories SET {",".join(k + "=?" for k in fields)} WHERE id=?', (*fields.values(), memory_id))
            self._write_labels(memory_id, data['tags'], data['aliases'])
        self.changed()
        return memory_id

    def save_memory(self, category_id, title, key, value, description='', enabled=True, memory_id=None, confirmed=False, **metadata):
        if memory_id:
            return self.update_memory(memory_id, confirmed=confirmed, category_id=category_id, title=title, key=key,
                                      value=value, description=description, enabled=enabled, **metadata)
        return self.create_memory(category_id, title, key, value, description, enabled, confirmed=confirmed, **metadata)

    def delete_memory(self, memory_id):
        with self.db:
            self.db.execute('DELETE FROM memories WHERE id=?', (memory_id,))
        self.changed()

    def record_access(self, memory_id):
        row = self._raw(memory_id)
        if not row or not self.applicable(row):
            return False
        with self.db:
            self.db.execute('UPDATE memories SET access_count=access_count+1,last_accessed_at=? WHERE id=?', (self.now(), memory_id))
        return True

    def get_by_key(self, key, consume=True, reveal=False):
        match = self.retriever.get_by_key(key, consume=consume, reveal=reveal)
        return match.memory if match else None

    get_memory_by_key = get_by_key

    def search(self, query, consume=True, **filters):
        return self.retriever.search(query, consume=consume, **filters)

    def retrieve_relevant(self, query, consume=True):
        return self.retriever.retrieve_relevant(query, consume=consume)

    def get_by_type(self, memory_type, consume=True):
        return self.retriever.retrieve_by_type(memory_type, consume=consume)

    def get_by_scope(self, memory_scope, consume=True):
        return self.retriever.retrieve_relevant(MemoryQuery(memory_scope=memory_scope), consume=consume)

    def set_profile(self, profile_id):
        self.profile_id = checked_text(profile_id, 'Profile', 100)

    def set_profile_value(self, field, value, category_id, confirmed=False, **metadata):
        field = normalize(checked_text(field, 'Profile field', 100))
        if not re.fullmatch(r'[a-z][a-z0-9_.]*', field):
            raise ValueError('Use a structured profile field.')
        key = field if field.startswith('user.') else 'user.' + field
        return self.create_memory(category_id, key[5:].replace('_', ' ').title(), key, value,
                                  memory_type=MemoryType.PROFILE, confirmed=confirmed, **metadata)

    def get_profile_value(self, field, consume=True):
        key = field if field.startswith('user.') else 'user.' + field
        return self.get_by_key(key, consume=consume)

    def set_context(self, key, value, category_id=None, temporary=False, expires_at=None, memory_scope='SESSION', lifetime='session', source='SYSTEM'):
        if category_id is None:
            category = self.db.execute("SELECT id FROM memory_categories WHERE name='Personal Information' AND sensitive=0").fetchone()
            if not category:
                raise ValueError('Create a non-sensitive Personal Information category first.')
            category_id = category[0]
        existing = self.find_existing(key)
        if existing and existing['memory_type'] != MemoryType.CONTEXT.value:
            raise MemoryConflict(MemoryConflictType.TYPE_CONFLICT, existing)
        return self.create_memory(category_id, key.replace('_', ' ').title(), key, value,
                                  memory_type=MemoryType.CONTEXT, source=source,
                                  memory_scope=MemoryScope.TEMPORARY if temporary else memory_scope,
                                  lifetime=MemoryLifetime.TEMPORARY if temporary else lifetime,
                                  expires_at=expires_at, confirmed=True)

    def cleanup_session(self, startup=False, notify=True):
        with self.db:
            cursor = self.db.execute('DELETE FROM memories WHERE lifetime=? AND (session_id IS NULL OR session_id<>?)' if startup else 'DELETE FROM memories WHERE lifetime=? AND session_id=?',
                                     (MemoryLifetime.SESSION.value, self.session_id))
        if cursor.rowcount and notify:
            self.changed()
        return cursor.rowcount

    def close_session(self):
        return self.cleanup_session()

    def expire_memories(self, delete=False, notify=True):
        stamp = self.now()
        count = self.db.execute('SELECT count(*) FROM memories WHERE expires_at IS NOT NULL AND expires_at<=?', (stamp,)).fetchone()[0]
        if delete and count:
            with self.db:
                self.db.execute('DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at<=?', (stamp,))
            if notify:
                self.changed()
        return count

    def create_relationship(self, source_memory_id, relationship_type, target_memory_id):
        kind = normalize(checked_text(relationship_type, 'Relationship type', 64)).replace(' ', '_')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', kind):
            raise ValueError('Use a simple relationship type.')
        if source_memory_id == target_memory_id or not self._raw(source_memory_id) or not self._raw(target_memory_id):
            raise ValueError('Choose two different existing memories.')
        existing = self.db.execute('SELECT id FROM memory_relationships WHERE source_memory_id=? AND relationship_type=? AND target_memory_id=?', (source_memory_id, kind, target_memory_id)).fetchone()
        if existing:
            return existing[0]
        relationship_id = str(uuid.uuid4())
        with self.db:
            self.db.execute('INSERT INTO memory_relationships VALUES (?,?,?,?,?)', (relationship_id, source_memory_id, kind, target_memory_id, self.now()))
        self.changed()
        return relationship_id

    def get_relationships(self, memory_id=None):
        sql = '''SELECT r.*,s.title AS source_title,t.title AS target_title,s.memory_key AS source_key,t.memory_key AS target_key
                 FROM memory_relationships r JOIN memories s ON s.id=r.source_memory_id JOIN memories t ON t.id=r.target_memory_id'''
        return self._rows(sql + (' WHERE r.source_memory_id=? OR r.target_memory_id=?' if memory_id else '') + ' ORDER BY r.created_at,r.id',
                          (memory_id, memory_id) if memory_id else ())

    def delete_relationship(self, relationship_id):
        with self.db:
            self.db.execute('DELETE FROM memory_relationships WHERE id=?', (relationship_id,))
        self.changed()

    def memory_health(self, unused_days=30):
        if not isinstance(unused_days, int) or unused_days < 1:
            raise ValueError('Unused memory age must be positive.')
        rows = self.list_memories(include_system=True)
        cutoff = (datetime.fromisoformat(self.now()) - timedelta(days=unused_days)).isoformat()
        return dict(total=len(rows), active=sum(bool(r['enabled']) and not r['expired'] for r in rows),
                    disabled=sum(not r['enabled'] for r in rows), expired=sum(r['expired'] for r in rows),
                    sensitive=sum(bool(r['sensitive']) for r in rows),
                    unused=sum(r['access_count'] == 0 and r['created_at'] < cutoff for r in rows))

    def export_memories(self):
        fields = ('title','memory_key','memory_value','description','enabled','category','memory_type','memory_scope',
                  'lifetime','importance','confidence','source','expires_at','scope_id','tags','aliases',
                  'created_at','updated_at','last_accessed_at','access_count')
        # Ephemeral operational session state and internal system records are not portable personal memories.
        rows = [r for r in self.list_memories(include_system=False) if not r['sensitive'] and r['lifetime'] != 'session']
        keys = {r['memory_key'] for r in rows}
        edges = [dict(source_key=e['source_key'], relationship_type=e['relationship_type'], target_key=e['target_key'])
                 for e in self.get_relationships() if e['source_key'] in keys and e['target_key'] in keys]
        return dict(version=2, memories=[{k:r[k] for k in fields} for r in rows], relationships=edges)

    def _import_data(self, record, version):
        old_fields = {'title','memory_key','memory_value','description','enabled','category'}
        new_fields = old_fields | {'memory_type','memory_scope','lifetime','importance','confidence','source','expires_at',
                                 'scope_id','tags','aliases','created_at','updated_at','last_accessed_at','access_count'}
        if not isinstance(record, dict) or set(record) - (old_fields if version == 1 else new_fields):
            raise ValueError('Invalid memory record properties.')
        category = checked_text(record.get('category'), 'Category', 100)
        stored = self.db.execute('SELECT * FROM memory_categories WHERE name=?', (category,)).fetchone()
        if stored and stored['sensitive']:
            raise ValueError('Sensitive categories cannot be imported from plain JSON.')
        fallback = self.db.execute('SELECT id FROM memory_categories WHERE sensitive=0 LIMIT 1').fetchone()
        if fallback is None:
            raise ValueError('Create a non-sensitive memory category first.')
        metadata = {k: record[k] for k in ('memory_type','memory_scope','lifetime','importance','confidence','expires_at','scope_id','tags','aliases') if k in record}
        if 'source' in record:
            MemorySource(record['source'])
        if 'memory_type' not in metadata:
            import_key = normalize(checked_text(record.get('memory_key'), 'Key', 200))
            if import_key.startswith('user.') or import_key in STANDARD_ALIASES['user.name']:
                metadata['memory_type'] = MemoryType.PROFILE
            elif import_key.startswith('preferred.'):
                metadata['memory_type'] = MemoryType.PREFERENCE
        metadata['source'] = MemorySource.IMPORT
        data = self._prepare(stored['id'] if stored else fallback[0], record.get('title'), record.get('memory_key'),
                             record.get('memory_value'), record.get('description', ''), record.get('enabled', 1), **metadata)
        data['category'] = category
        if data['lifetime'] == MemoryLifetime.SESSION.value:
            raise ValueError('Session memories cannot be imported from plain JSON.')
        for field in ('created_at','updated_at','last_accessed_at'):
            if field in record:
                timestamp(record[field], optional=field == 'last_accessed_at')
        count = record.get('access_count', 0)
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1_000_000_000:
            raise ValueError('Invalid memory usage count.')
        data['access_count'] = count
        data['last_accessed_at'] = timestamp(record.get('last_accessed_at'), optional=True)
        return data

    def _import_plan(self, payload):
        if (not isinstance(payload, dict) or isinstance(payload.get('version'), bool) or payload.get('version') not in (1, 2)
                or set(payload) - {'version','memories','relationships'} or not isinstance(payload.get('memories'), list)
                or len(payload['memories']) > 10000):
            raise ValueError('Invalid memory export.')
        relationships = payload.get('relationships', [])
        if not isinstance(relationships, list) or len(relationships) > 10000 or (payload['version'] == 1 and relationships):
            raise ValueError('Invalid memory relationships export.')
        summary = dict(new=0, duplicates=0, conflicts=0, invalid=0, records=[])
        plan, seen, alias_owners = [], {}, {}
        for index, record in enumerate(payload['memories']):
            try:
                data = self._import_data(record, payload['version'])
                key = data['memory_key']
                existing = self.find_existing(key)
                canonical = existing['memory_key'] if existing else key
                if canonical in seen:
                    prior = seen[canonical]
                    if prior['memory_value'] != data['memory_value'] or prior['memory_type'] != data['memory_type'] or prior['memory_scope'] != data['memory_scope'] or prior['scope_id'] != data['scope_id'] or prior['lifetime'] != data['lifetime']:
                        raise ValueError('Conflicting duplicate records within the import.')
                    status = 'duplicates'
                elif existing:
                    same = (not existing['sensitive'] and existing['memory_value'] == data['memory_value']
                            and existing['memory_type'] == data['memory_type'] and existing['memory_scope'] == data['memory_scope']
                            and existing['scope_id'] == data['scope_id'] and existing['lifetime'] == data['lifetime'])
                    status = 'duplicates' if same else 'conflicts'
                else:
                    status = 'new'
                if existing and existing['sensitive']:
                    raise ValueError('Plain imports cannot replace sensitive memories.')
                owner_id = existing['id'] if existing else canonical
                self._check_labels(owner_id, key, data['aliases'])
                for alias in [canonical, *data['aliases']]:
                    owner = alias_owners.get(alias)
                    if owner is not None and owner != canonical:
                        raise ValueError('Conflicting aliases within the import.')
                    alias_owners[alias] = canonical
                seen[canonical] = data
                data['memory_key'] = canonical
                summary[status] += 1
                summary['records'].append(dict(index=index, status=status, key=canonical))
                plan.append((status, data, existing))
            except (ValueError, TypeError, KeyError):
                summary['invalid'] += 1
                summary['records'].append(dict(index=index, status='invalid', reason='Invalid record or unsafe memory metadata.'))
        edges = []
        for index, edge in enumerate(relationships):
            try:
                if not isinstance(edge, dict) or set(edge) != {'source_key','relationship_type','target_key'}:
                    raise ValueError()
                source = normalize(checked_text(edge['source_key'], 'Source key', 200))
                target = normalize(checked_text(edge['target_key'], 'Target key', 200))
                kind = normalize(checked_text(edge['relationship_type'], 'Relationship type', 64)).replace(' ', '_')
                if source == target or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', kind):
                    raise ValueError()
                for key in (source, target):
                    if key not in seen:
                        existing = self.find_existing(key)
                        if not existing or existing['sensitive']:
                            raise ValueError()
                edges.append((source, kind, target))
            except (ValueError, TypeError, KeyError):
                summary['invalid'] += 1
                summary['records'].append(dict(index=f'relationship:{index}', status='invalid', reason='Invalid relationship.'))
        return summary, plan, edges

    def preview_import(self, payload):
        return self._import_plan(payload)[0]

    def import_memories(self, payload, confirm_conflicts=False, strict=False):
        summary, plan, edges = self._import_plan(payload)
        if summary['invalid'] or (summary['conflicts'] and not confirm_conflicts) or (strict and summary['duplicates']):
            raise ValueError('Import contains invalid, duplicate, or conflicting memories; review the import summary first.')
        with self.db:
            for status, data, existing in plan:
                if status == 'duplicates':
                    continue
                category = data.pop('category')
                self.db.execute('INSERT OR IGNORE INTO memory_categories VALUES (?,?,0)', (str(uuid.uuid4()), category))
                data['category_id'] = self.db.execute('SELECT id FROM memory_categories WHERE name=?', (category,)).fetchone()[0]
                last_accessed_at = data.pop('last_accessed_at')
                access_count = data.pop('access_count')
                if status == 'new':
                    memory_id = self._create(data)
                else:
                    memory_id = existing['id']
                    fields = {k:v for k,v in data.items() if k not in ('tags','aliases','sensitive')}
                    fields['updated_at'] = self.now()
                    self.db.execute(f'UPDATE memories SET {",".join(k + "=?" for k in fields)} WHERE id=?', (*fields.values(), memory_id))
                    self._write_labels(memory_id, data['tags'], data['aliases'])
                self.db.execute('UPDATE memories SET last_accessed_at=?,access_count=? WHERE id=?', (last_accessed_at, access_count, memory_id))
            for source, kind, target in edges:
                source_row, target_row = self.find_existing(source), self.find_existing(target)
                self.db.execute('INSERT OR IGNORE INTO memory_relationships VALUES (?,?,?,?,?)',
                                (str(uuid.uuid4()), source_row['id'], kind, target_row['id'], self.now()))
        self.changed()
        return summary

    @staticmethod
    def validate_backup(connection):
        """Validate data in a restore candidate without cleaning or changing it."""
        service = MemoryService.__new__(MemoryService)
        service.db = connection
        service.db.row_factory = sqlite3.Row
        service.clock = lambda: datetime.now(timezone.utc)
        service.session_id = 'backup-validation'
        service.profile_id = 'default'
        for row in service._rows(SELECT_MEMORY):
            checked_text(row['id'], 'Memory identifier', 100)
            for field in ('created_at','updated_at'):
                timestamp(row[field])
            timestamp(row['last_accessed_at'], optional=True)
            timestamp(row['expires_at'], optional=True)
            if isinstance(row['access_count'], bool) or not isinstance(row['access_count'], int) or not 0 <= row['access_count'] <= 1_000_000_000:
                raise ValueError('Invalid memory usage count in backup.')
            if row['sensitive']:
                if not isinstance(row['memory_value'], str) or not row['memory_value'].startswith('dpapi:') or len(row['memory_value']) > 40000:
                    raise ValueError('Invalid protected memory in backup.')
            else:
                checked_text(row['memory_value'], 'Value', 20000)
            data = service._prepare(row['category_id'], row['title'], row['memory_key'], MASK if row['sensitive'] else row['memory_value'],
                                   row['description'], row['enabled'], memory_type=row['memory_type'], memory_scope=row['memory_scope'],
                                   lifetime=row['lifetime'], importance=row['importance'], confidence=row['confidence'], source=row['source'],
                                   expires_at=row['expires_at'], scope_id=row['scope_id'])
            if row['lifetime'] == 'session':
                checked_text(row['session_id'], 'Session identifier', 100)
            elif row['session_id'] is not None:
                raise ValueError('Persistent memory cannot belong to a session.')
            if row['lifetime'] == 'temporary' and row['expires_at'] is None:
                raise ValueError('Temporary memory requires an expiry time.')
            if row['memory_scope'] == 'PROFILE' and not row['scope_id']:
                raise ValueError('Profile memory requires an owner.')
            for field in ('memory_scope', 'lifetime', 'scope_id', 'expires_at'):
                if data[field] != row[field]:
                    raise ValueError('Inconsistent memory lifecycle metadata in backup.')
        for row in service._rows('SELECT * FROM memory_tags'):
            if labels([row['tag']], 'Tag') != [row['tag']]:
                raise ValueError('Invalid tag in backup.')
        for row in service._rows('SELECT * FROM memory_aliases'):
            if normalize(checked_text(row['alias'], 'Alias', 150)) != row['normalized_alias'] or labels([row['normalized_alias']], 'Alias', 150) != [row['normalized_alias']]:
                raise ValueError('Invalid alias in backup.')
            owner = connection.execute('SELECT id FROM memories WHERE lower(memory_key)=?', (row['normalized_alias'],)).fetchone()
            if owner and owner[0] != row['memory_id']:
                raise ValueError('Alias conflicts with a memory key in backup.')
        for row in service._rows('SELECT * FROM memory_relationships'):
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', row['relationship_type']):
                raise ValueError('Invalid relationship in backup.')
            timestamp(row['created_at'])
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Orphaned memory metadata in backup.')
