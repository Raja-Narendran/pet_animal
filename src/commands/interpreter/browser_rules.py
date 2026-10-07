"""Offline browser fallback grammar; no DNS, network calls or OS actions."""
import re
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from ...config.settings import settings
from .models import CommandIntent, InterpretationResult, IntentType, MatchReason
from .patterns import OPEN_VERBS, SEARCH_PREFIXES, MUSIC_PREFIXES
from ..voice_phrases import VERBS, AUXILIARIES


DIRECT_WEBSITE_SOURCE = 'direct_website'
FALLBACK_SEARCH_SOURCE = 'fallback_search'
# Incomplete explicit commands must never silently become web searches.
COMMAND_PREFIXES = OPEN_VERBS | frozenset(SEARCH_PREFIXES + MUSIC_PREFIXES) | frozenset({
    'help', 'commands', 'remember', 'save', 'forget', 'recall', 'delete', 'remove',
    'locate', 'select', 'choose', 'cancel', 'yes', 'no', 'workflow', 'routine',
    'cmd', 'powershell', 'pwsh', 'rm', 'del',
}) | frozenset().union(*VERBS.values())
SCHEME = re.compile(r'^[a-z][a-z0-9+.-]*:', re.I)
LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.I)


@lru_cache(maxsize=1)
def top_level_domains():
    """IANA snapshot shipped with the application, including frozen builds."""
    path = settings.BASE_DIR / 'assets/domains/tlds-alpha-by-domain.txt'
    return frozenset(line.strip().casefold() for line in path.read_text(encoding='ascii').splitlines()
                     if line.strip() and not line.startswith('#'))


def website_url(value):
    """Return canonical HTTPS for a complete domain/address, or None."""
    if (not isinstance(value, str) or not value or len(value) > 500
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or '\\' in value):
        return None
    explicit = bool(SCHEME.match(value)) and not re.fullmatch(r'[^:/?#@]+:443', value)
    # Bare input is a hostname, optionally with the standard HTTPS port.
    if not explicit and any(c in value for c in '/?#@'):
        return None
    try:
        parsed = urlsplit(value if explicit else 'https://' + value)
        if (parsed.scheme != 'https' or not parsed.hostname or '@' in parsed.netloc
                or parsed.port not in (None, 443) or parsed.netloc.endswith(':')):
            return None
        host = parsed.hostname.encode('idna').decode('ascii').lower()
        labels = host.split('.')
        if len(host) > 253 or len(labels) < 2 or any(not LABEL.fullmatch(label) for label in labels):
            return None
        for label in labels:
            if label.startswith('xn--'):
                if label.encode('ascii').decode('idna').encode('idna').decode('ascii') != label:
                    return None
        if labels[-1] not in top_level_domains():
            return None
        authority = host + (':443' if parsed.port == 443 else '')
        return urlunsplit(('https', authority, parsed.path, parsed.query, parsed.fragment))
    except (ValueError, UnicodeError):
        return None


def browser_fallback(raw, normalized):
    """Called only after registered phrases and existing intents fail to match."""
    value = raw.strip()
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in raw):
        return InterpretationResult(reason=MatchReason.INVALID_INPUT)
    try:
        url = website_url(value)
    except OSError:
        return InterpretationResult(reason=MatchReason.UNAVAILABLE_COMMAND)
    if url:
        intent = CommandIntent(IntentType.OPEN_WEBSITE, url, source=DIRECT_WEBSITE_SOURCE)
        return InterpretationResult(True, intent, reason=MatchReason.SMART_MATCH, confidence=1.0)
    if SCHEME.match(value) or value.startswith(('//', '\\')):
        return InterpretationResult(reason=MatchReason.UNSUPPORTED_TARGET)
    phrase = normalized.text
    words = phrase.split()
    if (any(phrase == prefix or phrase.startswith(prefix + ' ') for prefix in COMMAND_PREFIXES)
            or (words and words[-1] in {'delete', 'remove', 'cmd', 'powershell', 'pwsh', 'rm', 'del'})
            or (set(raw.casefold().split()) & AUXILIARIES and
                set(words) & {'delete', 'remove'})):
        return InterpretationResult()
    intent = CommandIntent(IntentType.WEB_SEARCH, 'google', value, source=FALLBACK_SEARCH_SOURCE)
    return InterpretationResult(True, intent, reason=MatchReason.SMART_MATCH, confidence=1.0)
