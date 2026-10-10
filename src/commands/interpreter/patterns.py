"""Central semantic vocabulary shared by smart and compatibility parsers."""
from ..voice_phrases import VERBS


OPEN_VERBS = frozenset(VERBS['open'] | {'bring up', 'show', 'go to', 'take me to'})
APPLICATION_ALIASES = {
    'chrome': {'chrome', 'google chrome', 'browser', 'my browser'},
    'notepad': {'notepad', 'note pad'},
    'calculator': {'calculator', 'calc'},
    'explorer': {'explorer', 'file explorer', 'windows explorer'},
    'vscode': {'vscode', 'vs code', 'visual studio code', 'code editor', 'my code editor', 'code'},
}
WEBSITE_ALIASES = {'youtube': {'youtube', 'you tube'}, 'google': {'google'}}
LOW_CONFIDENCE_ALIASES = frozenset({'code'})
SEARCH_PREFIXES = ('search google for', 'search on google', 'search google', 'search for',
                   'look up', 'search', 'find', 'google')
MUSIC_PREFIXES = ('play on youtube', 'youtube play', 'play song', 'play music', 'play')
HELP_PHRASES = frozenset({'help', 'show help', 'commands', 'what can you do', '?'})


def music_request(phrase):
    """Return provider override and song; None means no music grammar matched."""
    for prefix in MUSIC_PREFIXES:
        if phrase == prefix or phrase.startswith(prefix + ' '):
            provider = 'youtube' if prefix in ('play on youtube', 'youtube play') else None
            song = phrase[len(prefix):].strip()
            for name in ('spotify', 'youtube'):
                suffix = ' on ' + name
                if song.endswith(suffix):
                    provider, song = name, song[:-len(suffix)].strip()
                    break
                if song == 'on ' + name:
                    provider, song = name, ''
                    break
            return provider, song
    return None
