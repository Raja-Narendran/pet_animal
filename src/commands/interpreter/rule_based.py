"""Anchored templates, explicit verbs and whole-target aliases; no fuzzy execution."""
import re
from .base import IntentInterpreter
from .models import CommandIntent, InterpretationResult, IntentType, MatchReason
from .normalizer import normalize_input
from .patterns import (APPLICATION_ALIASES, WEBSITE_ALIASES, OPEN_VERBS,
                       LOW_CONFIDENCE_ALIASES, SEARCH_PREFIXES, MUSIC_PREFIXES, HELP_PHRASES)
from ..voice_phrases import NAME_ALIASES


class RuleBasedIntentInterpreter(IntentInterpreter):
    def __init__(self, application_aliases=None, website_aliases=None):
        self.application_aliases = APPLICATION_ALIASES if application_aliases is None else application_aliases
        self.website_aliases = WEBSITE_ALIASES if website_aliases is None else website_aliases

    @staticmethod
    def _match(kind, target=None, value=None, confidence=0.96):
        intent = CommandIntent(kind, target, value, confidence)
        return InterpretationResult(True, intent, reason=MatchReason.SMART_MATCH, confidence=confidence)

    def interpret(self, text: str) -> InterpretationResult:
        normalized = normalize_input(text)
        if not normalized.valid:
            return InterpretationResult(reason=MatchReason.INVALID_INPUT)
        if normalized.negated:
            return InterpretationResult(reason=MatchReason.NEGATED_COMMAND)
        phrase = normalized.text
        if phrase in HELP_PHRASES or text.strip() == '?':
            return self._match(IntentType.SHOW_HELP)
        if phrase in {'what is my name', 'tell me my name', 'do you remember my name'}:
            return self._match(IntentType.MEMORY_QUERY, target='user.name')
        # Values are extracted from the original text to preserve the name's casing.
        memory = re.fullmatch(r'(?:remember|save)\s+my\s+name\s+as\s+(.+)|my\s+name\s+is\s+(.+?),?\s+remember\s+that[.!]?', text.strip(), re.IGNORECASE)
        if memory:
            return self._match(IntentType.MEMORY_STORE, target='user.name', value=memory[1] or memory[2])
        for kind, prefixes in ((IntentType.WEB_SEARCH, SEARCH_PREFIXES), (IntentType.PLAY_MEDIA, MUSIC_PREFIXES)):
            for prefix in prefixes:
                if phrase.startswith(prefix + ' '):
                    value = phrase[len(prefix):].strip()
                    if kind == IntentType.PLAY_MEDIA and value.endswith(' on youtube'):
                        value = value[:-11].strip()
                    if value:
                        return self._match(kind, 'google' if kind == IntentType.WEB_SEARCH else 'youtube', value)
        candidate = None
        confidence = 0.96
        for verb in sorted(OPEN_VERBS, key=len, reverse=True):
            if phrase.startswith(verb + ' '):
                candidate = phrase[len(verb):].strip()
                break
        if candidate is None:
            # An explicit need is a supported request, rather than a bare entity guess.
            if phrase.startswith('i need '):
                candidate = phrase[7:]
                confidence = 0.90
            else:
                return InterpretationResult()
        if candidate.startswith('the '):
            candidate = candidate[4:]
        if candidate.endswith(' ah'):
            candidate = candidate[:-3]
        candidate = NAME_ALIASES.get(candidate, candidate)
        matches = [(kind, target) for kind, aliases in ((IntentType.OPEN_APPLICATION, self.application_aliases),
                                                       (IntentType.OPEN_WEBSITE, self.website_aliases))
                   for target, names in aliases.items() if candidate in names]
        if len(matches) > 1:
            return InterpretationResult(reason=MatchReason.AMBIGUOUS_TARGET)
        if not matches:
            return InterpretationResult(reason=MatchReason.UNSUPPORTED_TARGET)
        kind, target = matches[0]
        if candidate in LOW_CONFIDENCE_ALIASES:
            confidence = 0.80
        elif candidate != target:
            confidence = min(confidence, 0.90)
        return self._match(kind, target, confidence=confidence)
