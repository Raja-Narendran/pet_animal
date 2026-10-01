"""Explicit Tamil/English speech templates; never infer arbitrary actions."""
import re
import unicodedata

AUXILIARIES = {'பண்ணு', 'பண்ணுங்க', 'பண்ணுங்கள்', 'செய்', 'செய்யு', 'செய்யுங்க',
                'செய்யுங்கள்', 'pannu', 'pannunga', 'pannungal', 'pannum', 'பண்ண', 'செய்ய'}
POLITE = {'please', 'kindly', 'ப்ளீஸ்', 'தயவுசெய்து', 'எனக்கு'}
MUSIC_WORDS = {'பாட்டு', 'பாடல்', 'பாட்டை', 'பாடலை', 'song', 'music', 'paattu', 'pattu', 'paadal'}
VERBS = {
    'open': {'open', 'launch', 'start', 'run', 'ஓபன்', 'ஓப்பன்', 'திற', 'திறக்க', 'திறங்க', 'திறங்கப்பா', 'திறக்கவும்', 'thira', 'thirandhu'},
    'play': {'play', 'பிளே', 'ப்ளே', 'பிலே', 'போடு', 'போடுங்க', 'போடுங்கள்', 'இயக்கு', 'இயக்கவும்', 'podu', 'podunga'},
    'search': {'search', 'சர்ச்', 'செர்ச்', 'தேடு', 'தேடுங்க', 'தேடுங்கள்', 'தேடவும்', 'thedu', 'thedunga'},
}
NAME_ALIASES = {'குரோம்': 'chrome', 'க்ரோம்': 'chrome', 'கூகுள் குரோம்': 'google chrome',
          'கூகுள்': 'google', 'யூடியூப்': 'youtube', 'யூட்யூப்': 'youtube',
          'நோட்பேட்': 'notepad', 'கால்குலேட்டர்': 'calculator', 'கணிப்பான்': 'calculator',
          'விஎஸ் கோடு': 'vs code', 'ஷேப் ஆஃப் யூ': 'shape of you'}
LOCATIONS = ('on youtube', 'in youtube', 'youtube ல', 'youtube-ல', 'youtubeல',
              'யூடியூபில்', 'யூடியூப் ல', 'யூடியூப்-ல', 'யூடியூப்ல', 'google ல', 'google-ல', 'கூகுளில்')


def normalize_language_text(phrase):
    """Normalize speech punctuation without deleting operators or payload words."""
    normalized = unicodedata.normalize('NFC', phrase).casefold().replace('’', "'")
    words = [word.strip('.,!?।') for word in normalized.split()]
    return ' '.join(word for word in words if word)


def has_negation(phrase):
    """Reject command negation; negative words inside search/song payloads are data."""
    normalized = normalize_language_text(phrase)
    if re.search(r'(?<!\w)(?:vendam|vendaam|vendumilla|pannathe|pannadha|pannadhe|pannaathe|pannathinga|thirakkathe|வேண்டாம்|வேண்டமா|பண்ணாதே|பண்ணாதீங்க|பண்ணாதீர்கள்|திறக்காதே|திறக்காதீர்கள்)(?!\w)', normalized):
        return True
    negative = re.search(r"\b(?:don't|dont|do not|doesn't|didn't|cannot|can't|never|not|no)\b", normalized)
    if not negative:
        return False
    verbs = set().union(*VERBS.values()) | {'bring', 'go', 'take', 'show', 'need', 'find', 'look', 'remember', 'save'}
    action = next((word for word in normalized.split() if word in verbs), None)
    if action in VERBS['play'] | VERBS['search'] | {'find', 'look', 'google'}:
        # A leading action scopes its following free-form value. Do not erase it.
        return negative.start() < normalized.find(action) or normalized.endswith((" don't", ' do not', ' not'))
    return True


def normalize_mixed_voice(phrase):
    if has_negation(phrase):
        return normalize_language_text(phrase)
    normalized = normalize_language_text(phrase)
    words = normalized.split()
    words = [word for word in words if word]
    while words and words[0] in POLITE:
        words.pop(0)
    payload_first = bool(words and words[0] in VERBS['play'] | VERBS['search'] | {'find', 'look', 'google'})
    trailing = AUXILIARIES if payload_first else POLITE | AUXILIARIES
    while words and words[-1] in trailing:
        words.pop()
    normalized = ' '.join(words)
    for location in LOCATIONS:
        if normalized.startswith(location + ' '):
            normalized = normalized[len(location):].strip()
        if normalized.endswith(' ' + location):
            normalized = normalized[:-len(location)].strip()
    words = normalized.split()
    for action, verbs in VERBS.items():
        payload = None
        if words and words[0] in verbs:
            payload = words[1:]
        elif words and words[-1] in verbs:
            payload = words[:-1]
        if payload is not None:
            if action == 'play':
                # Remove command filler only at the edges; preserve words in song names.
                while payload and payload[0] in MUSIC_WORDS:
                    payload.pop(0)
                while payload and payload[-1] in MUSIC_WORDS:
                    payload.pop()
            target = ' '.join(payload)
            if not target:
                return normalized
            target = NAME_ALIASES.get(target, target)
            return action + ' ' + target
    return NAME_ALIASES.get(normalized, normalized)
