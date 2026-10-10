"""Explicit memory templates; values remain untouched and no data is retrieved here."""
import re
from ..voice_phrases import POLITE


# Friendly names map onto the same structured keys used by the memory service.
MEMORY_TARGETS = {
    'user.name': ('PROFILE', {'my name', 'name', 'user name'}),
    'user.nickname': ('PROFILE', {'my nickname', 'nickname'}),
    'user.preferred_language': ('PROFILE', {'my language', 'my preferred language', 'preferred language'}),
    'user.timezone': ('PROFILE', {'my timezone', 'my time zone', 'timezone'}),
    'user.work_project': ('PROFILE', {'my work project', 'work project'}),
    'preferred.browser': ('PREFERENCE', {'my browser', 'my preferred browser', 'preferred browser', 'default browser', 'browser preference'}),
    'preferred.editor': ('PREFERENCE', {'my editor', 'my code editor', 'my preferred editor', 'preferred editor', 'preferred code editor', 'my preferred code editor', 'preferred.code_editor'}),
    'preferred.music_service': ('PREFERENCE', {'my music service', 'my preferred music service', 'preferred music service'}),
    'preferred.music_app': ('PREFERENCE', {'my music app', 'my preferred music app', 'preferred music app'}),
    'preferred.theme': ('PREFERENCE', {'my theme', 'my preferred theme', 'preferred theme'}),
    'project.folder': ('KNOWLEDGE', {'my project folder', 'project folder'}),
    'project.pet_animal.path': ('KNOWLEDGE', {'my pet animal project path', 'my pet animal project folder', 'pet animal project path'}),
    'work.default_repo': ('KNOWLEDGE', {'my default repo', 'my default repository', 'default repo'}),
    'current_project': ('CONTEXT', {'my current project', 'current project'}),
    'current_task': ('CONTEXT', {'my current task', 'current task'}),
    'important.note': ('NOTE', {'note', 'my note', 'important note', 'my important note'}),
}
PREFERENCE_TARGETS = {
    'my browser': 'preferred.browser',
    'my preferred browser': 'preferred.browser',
    'my editor': 'preferred.editor',
    'my code editor': 'preferred.editor',
    'my preferred editor': 'preferred.editor',
    'my preferred code editor': 'preferred.editor',
}
QUERY_PHRASES = {
    'what browser do i prefer': 'preferred.browser',
    'which browser do i prefer': 'preferred.browser',
    'what editor do i prefer': 'preferred.editor',
    'which editor do i prefer': 'preferred.editor',
    'do you remember my name': 'user.name',
}
RAW_PREFIXES = tuple(sorted(POLITE | {'can you', 'could you', 'would you', 'will you'}, key=len, reverse=True))


def _raw_command(text):
    """Remove only request prefixes, preserving every character in stored values."""
    raw = text.strip()
    changed = True
    while changed:
        changed = False
        for prefix in RAW_PREFIXES:
            match = re.match(re.escape(prefix) + r'\s+', raw, re.IGNORECASE)
            if match:
                raw = raw[match.end():]
                changed = True
                break
    return raw


def memory_target(value):
    """Resolve anchored friendly fields or an explicit structured key."""
    normalized = ' '.join(value.casefold().split())
    for key, (kind, aliases) in MEMORY_TARGETS.items():
        if normalized == key or normalized in aliases:
            return key, kind
    if re.fullmatch(r'[a-z][a-z0-9_]*(?:[.][a-z][a-z0-9_-]*)+', normalized):
        prefix = normalized.partition('.')[0]
        kind = {'user': 'PROFILE', 'preferred': 'PREFERENCE', 'habit': 'HABIT',
                'relationship': 'RELATIONSHIP', 'note': 'NOTE', 'context': 'CONTEXT'}.get(prefix, 'KNOWLEDGE')
        # Operational system fields are managed by documented service APIs.
        if prefix != 'system':
            return normalized, kind
    return None


def memory_store_parts(text):
    """Return (key, type, raw value) only for an explicit supported storage command."""
    raw = _raw_command(text)
    legacy = re.fullmatch(r'my\s+name\s+is\s+(.+?),?\s+remember\s+that[.!]?', raw, re.IGNORECASE)
    if legacy:
        return 'user.name', 'PROFILE', legacy[1].strip()
    note = re.fullmatch(r'(?:remember|save)\s+(?:this\s+)?(?:important\s+)?note\s*:\s*(.+)', raw, re.IGNORECASE)
    if note:
        return 'important.note', 'NOTE', note[1].strip()
    match = re.fullmatch(r'(?:remember|save)\s+(?:that\s+)?(.+?)(?:\s+(?:as|is)\s+|\s*=\s*)(.+)', raw, re.IGNORECASE)
    if not match:
        return None
    target = memory_target(match[1])
    if target and match[2].strip():
        return target[0], target[1], match[2].strip()
    return None


def _explicit_alias(value):
    alias = ' '.join(value.casefold().split())
    if alias and len(alias) <= 200 and not any(ord(character) < 32 for character in alias):
        return alias, 'KNOWLEDGE'
    return None


def memory_query_target(phrase):
    if phrase in QUERY_PHRASES:
        return memory_target(QUERY_PHRASES[phrase])
    explicit = re.fullmatch(r'(?:recall memory|what do you remember about)\s+(.+)', phrase)
    if explicit:
        return memory_target(explicit[1]) or _explicit_alias(explicit[1])
    match = re.fullmatch(r"(?:what is|what's|tell me|show me|recall)\s+(.+)", phrase)
    return (memory_target(match[1]) or _explicit_alias(match[1])) if match else None


def memory_forget_target(phrase):
    explicit = re.fullmatch(r'(?:forget|delete|remove)\s+memory\s+(.+)', phrase)
    if explicit:
        if explicit[1] in {'everything', 'all', 'all memories', '*'}:
            return None
        return memory_target(explicit[1]) or _explicit_alias(explicit[1])
    match = re.fullmatch(r'forget\s+(.+)', phrase)
    return memory_target(match[1]) if match else None


def memory_panel_query(phrase):
    """Anchored requests for saved passwords/cards; no retrieval or fuzzy matching."""
    from .models import CommandIntent, IntentType

    request = re.sub(r"^(?:what is|what's|tell me|show me|show|recall|get|give me)\s+", '', phrase)
    request = re.sub(r'^(?:list|display)\s+', '', request)
    request = re.sub(r'^all\s+', '', request)
    request = re.sub(r'^(?:my|the)\s+', '', request)
    password_lists = {'passwords', 'saved passwords', 'all passwords'}
    card_lists = {'cards', 'card details', 'credit cards', 'debit cards',
                  'credit card details', 'debit card details',
                  'credit and debit cards', 'credit and debit card details'}
    if request in password_lists | card_lists:
        kind = 'password' if request in password_lists else 'card'
        return CommandIntent(IntentType.MEMORY_QUERY, kind, source='memory_panel', action='LIST')
    # Do not treat searches, storage, or launch commands as credential lookups.
    if re.match(r'^(?:search|find|open|launch|start|save|remember|forget|delete|remove)\b', request):
        return None
    field = None
    kind = None
    target = None
    match = re.fullmatch(r"(?:my\s+)?(.+?)(?:['’]s)?\s+password", request)
    if match:
        kind, target = 'password', match[1]
    else:
        match = re.fullmatch(r'password\s+(?:for|of)\s+(?:my\s+)?(.+)', request)
        if match:
            kind, target = 'password', match[1]
    if kind is None:
        field_match = re.fullmatch(r'(card number|cvv|cvc|expiry|expiry date|expiration date)\s+(?:for|of)\s+(?:my\s+)?(.+)', request)
        suffix_match = re.fullmatch(r"(?:my\s+)?(.+?)(?:['’]s)?\s+(card number|cvv|cvc|expiry|expiry date|expiration date)", request)
        if field_match or suffix_match:
            label, target = (field_match[1], field_match[2]) if field_match else (suffix_match[2], suffix_match[1])
            field = 'card_number' if label == 'card number' else 'cvv' if label in ('cvv', 'cvc') else 'expiry'
            kind = 'card'
        else:
            match = re.fullmatch(r"(?:my\s+)?(.+?)(?:['’]s)?\s+card(?:\s+details)?", request)
            if match:
                kind, target = 'card', match[1]
    if not kind or not target or len(target) > 200:
        return None
    return CommandIntent(IntentType.MEMORY_QUERY, target, source='memory_panel', action='LOOKUP',
                         filters=(('kind', kind), ('field', field or '')))
