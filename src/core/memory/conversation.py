"""Short-lived pet memory choices. Plaintext is never retained in a result/session."""
import re
import time
import uuid

from .service import normalize

CARD_FIELDS = (
    ('card_number', 'Card number'),
    ('cvv', 'CVV'),
    ('expiry', 'Expiry'),
)
CARD_LABELS = {
    'card number': 'card_number', 'number': 'card_number',
    'cvv number': 'cvv', 'cvv': 'cvv', 'cvc': 'cvv',
    'expiry date': 'expiry', 'expiry': 'expiry', 'expiration date': 'expiry',
}


def memory_kind(row):
    category = normalize(row['category'])
    if 'password' in category and 'card' in category:
        return 'card' if re.search(r'\bcard\b', normalize(row['title']).replace('.', ' ')) or row['memory_key'].endswith('.card') else 'password'
    if 'card' in category:
        return 'card'
    if 'password' in category:
        return 'password'
    return 'value'


def name_form(value, kind):
    value = normalize(value).replace('.', ' ').replace('_', ' ')
    value = re.sub(r"['’]s\b", '', value)
    value = re.sub(r'^(?:my|the)\s+', '', value)
    ending = r'\s+password$' if kind == 'password' else r'\s+card(?:\s+details)?$' if kind == 'card' else r'(?!)'
    return re.sub(ending, '', value).strip()


def matching_memories(service, target, kind):
    """Match names/keys/aliases exactly, within the requested category and scope."""
    rows = [row for row in service.list_memories(enabled=True, include_expired=False)
            if service.applicable(row) and memory_kind(row) == kind]
    if target is None:
        return sorted(rows, key=lambda row: (normalize(row['title']), row['id']))
    target = name_form(target, kind)
    return [row for row in rows if target in {
        name_form(name, kind) for name in (row['title'], row['memory_key'], *row['aliases'])
    }]


def mask_password(value):
    # Short secrets must not reveal most or all of their characters.
    if len(value) <= 6:
        return '****'
    if len(value) < 10:
        return value[:1] + '****' + value[-1:]
    return value[:3] + '****' + value[-3:]


def card_values(value):
    """Read the labeled text format written by the Manager, without guessing fields."""
    fields = {}
    for line in value.splitlines():
        label, separator, data = line.partition(':')
        field = CARD_LABELS.get(normalize(label))
        if separator and field and data.strip():
            if field in fields:
                raise ValueError('This card has duplicate fields. Review it in the Memory Manager.')
            fields[field] = data.strip()
    return fields


class MemoryConversation:
    TTL = 120

    def __init__(self, service):
        self.service = service
        self.clear()

    def clear(self):
        self.token = None
        self.rows = {}
        self.allowed = {}
        self.kind = None
        self.field = None
        self.list_available = False
        self.context = None
        self.deadline = 0

    def _context(self):
        return (self.service.profile_id, self.service.active_pet_profile(), self.service.session_id)

    @staticmethod
    def _signature(row):
        return tuple(row[key] for key in (
            'title', 'memory_key', 'category_id', 'sensitive', 'updated_at',
            'memory_scope', 'scope_id', 'lifetime', 'session_id', 'expires_at',
        ))

    def _validate(self, token):
        if (not self.token or token != self.token or time.monotonic() >= self.deadline
                or self.context != self._context()):
            self.clear()
            raise ValueError('These memory choices expired. Ask the pet again.')

    def _row(self, token, memory_id):
        self._validate(token)
        saved = self.rows.get(memory_id)
        row = self.service.get_memory(memory_id)
        if (not saved or not row or not self.service.applicable(row)
                or self._signature(row) != self._signature(saved)):
            raise ValueError('This memory changed or is unavailable. Ask the pet again.')
        return row

    def begin(self, rows, kind, *, listing=False, field=None):
        self.clear()
        if not rows:
            return dict(success=False, message='No saved passwords found.' if kind == 'password'
                        else 'No saved cards found.' if kind == 'card' else 'That memory has not been saved.',
                        pet_state='idle')
        self.token = str(uuid.uuid4())
        self.deadline = time.monotonic() + self.TTL
        self.context = self._context()
        fields = ('id', 'title', 'memory_key', 'category_id', 'sensitive', 'updated_at',
                  'memory_scope', 'scope_id', 'lifetime', 'session_id', 'expires_at')
        self.rows = {row['id']: {field: row[field] for field in fields} for row in rows}
        self.list_available = listing or len(rows) > 1
        self.kind = kind
        self.field = field
        self.allowed = {row['id']: {'value'} if kind != 'card' else set() for row in rows}
        try:
            return self.list(self.token) if listing or len(rows) > 1 else self.select(self.token, rows[0]['id'])
        except ValueError:
            self.clear()
            raise

    def _result(self, message, items, view):
        return dict(success=True, message=message, pet_state='success',
                    memory_token=self.token, memory_view=view, memory_items=items,
                    memory_can_back=view == 'detail' and self.list_available,
                    memory_remaining_ms=max(1, int((self.deadline - time.monotonic()) * 1000)))

    def list(self, token):
        self._validate(token)
        items = []
        for memory_id in tuple(self.rows):
            try:
                row = self._row(token, memory_id)
            except ValueError:
                if self.token is None:
                    raise
                self.allowed.pop(memory_id, None)
                continue
            self.allowed[memory_id] = {'value'} if self.kind != 'card' else set()
            items.append(dict(memory_id=memory_id, title=row['title'], preview='',
                              copy_field='value' if self.kind != 'card' else None,
                              selectable=True))
        self._validate(token)
        if not items:
            raise ValueError('These memories changed or are unavailable. Ask the pet again.')
        return self._result('Your passwords' if self.kind == 'password' else 'Your cards' if self.kind == 'card'
                            else 'Choose a memory', items, 'list')

    def select(self, token, memory_id):
        row = self._row(token, memory_id)
        # A named request or row click authorizes a masked preview of this record.
        revealed = self.service.get_memory(memory_id, reveal=True)
        value = revealed['memory_value']
        if self.kind == 'card':
            self.allowed = {key: set() for key in self.rows}
            values = card_values(value)
            if not values and not self.field:
                items = [dict(memory_id=memory_id, title='Saved details', preview='****',
                              copy_field='value', selectable=False)]
            else:
                fields = CARD_FIELDS if not self.field else tuple(pair for pair in CARD_FIELDS if pair[0] == self.field)
                items = []
                for field, label in fields:
                    data = values.get(field)
                    preview = 'Not saved'
                    if data:
                        digits = re.sub(r'\D', '', data)
                        preview = ('**** ' + digits[-4:] if field == 'card_number' and len(digits) > 4 else '****')
                    items.append(dict(memory_id=memory_id, title=label, preview=preview,
                                      copy_field=field if data else None, selectable=False))
        else:
            items = [dict(memory_id=memory_id, title='Password' if self.kind == 'password' else 'Value',
                          preview=mask_password(value), copy_field='value', selectable=False)]
        self.allowed[memory_id] = {item['copy_field'] for item in items if item['copy_field']}
        self._validate(token)
        if not self.service.record_access(memory_id):
            raise ValueError('This memory is unavailable. Ask the pet again.')
        return self._result(row['title'], items, 'detail')

    def copy_value(self, token, memory_id, field):
        """Return plaintext only for the particular copy action currently offered."""
        self._row(token, memory_id)
        if field not in self.allowed.get(memory_id, set()):
            raise ValueError('Choose an available copy button.')
        row = self.service.get_memory(memory_id, reveal=True)
        value = row['memory_value']
        if field != 'value':
            value = card_values(value).get(field)
        if value is None:
            raise ValueError('This field is no longer available. Ask the pet again.')
        self._validate(token)
        if not self.service.record_access(memory_id):
            raise ValueError('This memory is unavailable. Ask the pet again.')
        return value
