"""Conservative, language-aware normalization; exact matching uses the original text."""
from dataclasses import dataclass
from ..voice_phrases import POLITE, has_negation, normalize_language_text, normalize_mixed_voice
from .patterns import MUSIC_PREFIXES, SEARCH_PREFIXES


@dataclass(frozen=True)
class NormalizedInput:
    text: str = ''
    negated: bool = False
    valid: bool = True


PREFIXES = tuple(sorted(POLITE | {'can you', 'could you', 'would you', 'will you'}, key=len, reverse=True))
SUFFIXES = tuple(sorted(POLITE | {'for me'}, key=len, reverse=True))


def normalize_input(text: str) -> NormalizedInput:
    if not isinstance(text, str) or len(text) > 500 or any(ord(c) < 32 and c not in '\t' for c in text):
        return NormalizedInput(valid=False)
    negated = has_negation(text)
    normalized = normalize_language_text(text)
    if negated:
        return NormalizedInput(normalized, negated=True)
    # Only documented wrappers at the edges are filler. Embedded words stay intact.
    changed = True
    while changed:
        changed = False
        for prefix in PREFIXES:
            if normalized.startswith(prefix + ' '):
                normalized = normalized[len(prefix):].strip()
                changed = True
                break
        is_payload = any(normalized.startswith(prefix + ' ') for prefix in MUSIC_PREFIXES + SEARCH_PREFIXES)
        if not is_payload:
            for suffix in SUFFIXES:
                if normalized.endswith(' ' + suffix):
                    normalized = normalized[:-len(suffix)].strip()
                    changed = True
                    break
    return NormalizedInput(normalize_mixed_voice(normalized))
