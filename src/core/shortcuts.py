"""Read-only application shortcut entries; targets are IDs, never executable paths."""
from dataclasses import dataclass


APPLICATION_NAMES = {
    'chrome': 'Chrome',
    'notepad': 'Notepad',
    'calculator': 'Calculator',
    'explorer': 'File Explorer',
    'vscode': 'VS Code',
}


@dataclass(frozen=True)
class ApplicationShortcut:
    target: str
    display_name: str
    aliases: tuple[str, ...]
    command_id: str


def match_shortcuts(entries, query):
    """Rank literal names and aliases without interpreting arbitrary command text."""
    if not isinstance(query, str) or len(query) > 500 or any(ord(c) < 32 for c in query):
        return []
    query = ' '.join(query.casefold().split())
    matches = []
    for entry in entries:
        names = (' '.join(name.casefold().split()) for name in (entry.display_name, *entry.aliases))
        ranks = [0 if name == query else 1 if name.startswith(query) else 2
                 for name in names if query in name]
        if ranks:
            matches.append((min(ranks), entry.display_name.casefold(), entry.target, entry))
    return [match[-1] for match in sorted(matches)]
