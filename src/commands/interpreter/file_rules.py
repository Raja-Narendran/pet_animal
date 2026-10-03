"""Filename grammar only. No filesystem access or search backend imports."""
import re
from pathlib import PureWindowsPath
from .models import CommandIntent, IntentType


def file_intent(text):
    if not isinstance(text, str) or len(text) > 500 or any(ord(c) < 32 for c in text):
        return None
    phrase = text.strip()
    phrase = re.sub(r'^(?:(?:can|could|would|will) you\s+|please\s+)+', '', phrase, flags=re.I)
    followup = phrase.casefold().rstrip('.!?').strip()
    actions = {'open it': 'OPEN_RESULT', 'open that': 'OPEN_RESULT', 'open the file': 'OPEN_RESULT',
               'open the folder': 'OPEN_RESULT', 'yes': 'CONFIRM', 'yes please': 'CONFIRM',
               'no': 'CANCEL', 'no thanks': 'CANCEL', 'cancel': 'CANCEL',
               'show results': 'LIST', 'list results': 'LIST', 'show all results': 'LIST',
               'next results': 'NEXT', 'previous results': 'PREVIOUS',
               'open the most recent one': 'OPEN_RECENT', 'open the latest one': 'OPEN_RECENT'}
    if followup in actions:
        return CommandIntent(IntentType.FILE_SEARCH, action=actions[followup])
    selected = re.fullmatch(r'(?:open|select|choose)\s+(?:result\s+)?(\d+)', followup)
    if selected:
        return CommandIntent(IntentType.FILE_SEARCH, target=selected[1], action='SELECT')
    project = re.fullmatch(r'(?:open\s+)?the\s+(.+?)\s+(?:one|result)', phrase.rstrip('.!?'), re.I)
    if project:
        return CommandIntent(IntentType.FILE_SEARCH, query=project[1].strip(), action='SELECT_PROJECT')
    shortcut = phrase.startswith('/')
    if shortcut:
        query = phrase[1:].strip()
    else:
        match = re.fullmatch(r'(?:find|locate|search files? for|search folders? for)\s+(.+)', phrase, re.I)
        if not match:
            return None
        query = match[1].strip()
    # Quoted names preserve punctuation and words such as "my" or "folder".
    folder = bool(re.match(r'^search folders? for\s', phrase, re.I))
    if not shortcut:
        query = re.sub(r'^(?:my|the)\s+', '', query, count=1, flags=re.I)
    prefix = re.match(r'^(file|folder|directory)\s+(.+)', query, re.I)
    if prefix:
        folder = prefix[1].casefold() != 'file'
        query = prefix[2].strip()
    suffix = re.fullmatch(r'(.+?)\s+(folder|directory)', query.rstrip('.!?'), re.I)
    if suffix:
        folder = True
        query = suffix[1].strip()
    if len(query) >= 2 and query[0] == query[-1] and query[0] in ('"', "'"):
        query = query[1:-1]
    else:
        query = query.rstrip('.?!')
    # Names, not paths or backend syntax. In particular, "find Salesforce CI/CD"
    # remains the existing web command; explicit slash queries never become web searches.
    if not valid_query(query):
        if shortcut:
            return CommandIntent(IntentType.FILE_SEARCH, query=query, action='FIND')
        return None
    filters = []
    if folder:
        filters.append(('kind', 'folder'))
    elif (extension := PureWindowsPath(query).suffix):
        filters.append(('extension', extension.casefold()))
    return CommandIntent(IntentType.FILE_SEARCH, query=query, filters=tuple(filters),
                         action='FIND')


def valid_query(query):
    return (isinstance(query, str) and bool(query.strip()) and len(query) <= 255
            and query not in ('.', '..') and not any(ord(c) < 32 or c in '\\/:<>"|*?' for c in query))
