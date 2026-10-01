"""Explicit Tamil/English speech templates; never infer arbitrary actions."""
import unicodedata

_AUXILIARIES = {'பண்ணு', 'பண்ணுங்க', 'பண்ணுங்கள்', 'செய்', 'செய்யு', 'செய்யுங்க',
                'செய்யுங்கள்', 'pannu', 'pannunga', 'pannungal', 'pannum', 'பண்ண', 'செய்ய'}
_POLITE = {'please', 'ப்ளீஸ்', 'தயவுசெய்து', 'எனக்கு'}
_MUSIC = {'பாட்டு', 'பாடல்', 'பாட்டை', 'பாடலை', 'song', 'music', 'paattu', 'pattu', 'paadal'}
_VERBS = {
    'open': {'open', 'ஓபன்', 'ஓப்பன்', 'திற', 'திறக்க', 'திறங்க', 'திறங்கப்பா', 'திறக்கவும்', 'thira'},
    'play': {'play', 'பிளே', 'ப்ளே', 'பிலே', 'போடு', 'போடுங்க', 'போடுங்கள்', 'இயக்கு', 'இயக்கவும்', 'podu', 'podunga'},
    'search': {'search', 'சர்ச்', 'செர்ச்', 'தேடு', 'தேடுங்க', 'தேடுங்கள்', 'தேடவும்', 'thedu', 'thedunga'},
}
_NAMES = {'குரோம்': 'chrome', 'க்ரோம்': 'chrome', 'கூகுள் குரோம்': 'google chrome',
          'கூகுள்': 'google', 'யூடியூப்': 'youtube', 'யூட்யூப்': 'youtube',
          'நோட்பேட்': 'notepad', 'கால்குலேட்டர்': 'calculator', 'கணிப்பான்': 'calculator',
          'விஎஸ் கோடு': 'vs code', 'ஷேப் ஆஃப் யூ': 'shape of you'}
_LOCATIONS = ('on youtube', 'in youtube', 'youtube ல', 'youtube-ல', 'youtubeல',
              'யூடியூபில்', 'யூடியூப் ல', 'யூடியூப்-ல', 'யூடியூப்ல', 'google ல', 'google-ல', 'கூகுளில்')


def normalize_mixed_voice(phrase):
    normalized = ' '.join(unicodedata.normalize('NFC', phrase).lower().split()).strip(' .!?।')
    words = [word.strip('.,!?;:') for word in normalized.split()]
    words = [word for word in words if word]
    while words and words[0] in _POLITE:
        words.pop(0)
    while words and words[-1] in _POLITE | _AUXILIARIES:
        words.pop()
    normalized = ' '.join(words)
    for location in _LOCATIONS:
        if normalized.startswith(location + ' '):
            normalized = normalized[len(location):].strip()
        if normalized.endswith(' ' + location):
            normalized = normalized[:-len(location)].strip()
    words = normalized.split()
    for action, verbs in _VERBS.items():
        payload = None
        if words and words[0] in verbs:
            payload = words[1:]
        elif words and words[-1] in verbs:
            payload = words[:-1]
        if payload is not None:
            if action == 'play':
                # Remove command filler only at the edges; preserve words in song names.
                while payload and payload[0] in _MUSIC:
                    payload.pop(0)
                while payload and payload[-1] in _MUSIC:
                    payload.pop()
            target = ' '.join(payload)
            if not target:
                return normalized
            target = _NAMES.get(target, target)
            return action + ' ' + target
    return _NAMES.get(normalized, normalized)
