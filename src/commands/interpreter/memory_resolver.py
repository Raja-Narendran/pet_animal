"""Resolve a remembered application only through current registered commands."""
from dataclasses import replace
from .models import AUTO_EXECUTE_THRESHOLD, InterpretationResult, IntentType, MatchReason
from .resolver import IntentResolver
from ...services.windows_launcher import WindowsLauncher


class MemoryResolver:
    """No SQL, decryption, persistence, OS paths, or operating-system execution."""

    FALLBACK_TARGETS = {'preferred.browser': 'chrome', 'preferred.editor': 'vscode'}

    def __init__(self, retriever):
        self.retriever = retriever
        self.command_resolver = IntentResolver()

    def resolve(self, intent, commands, application_aliases, consume=False):
        if intent.intent != IntentType.OPEN_APPLICATION or intent.target not in self.FALLBACK_TARGETS:
            return self.command_resolver.resolve(intent, commands)
        if not AUTO_EXECUTE_THRESHOLD <= intent.confidence <= 1.0:
            return InterpretationResult(False, intent, reason=MatchReason.LOW_CONFIDENCE, confidence=intent.confidence)
        key = intent.target
        # An unavailable saved preference must not silently become a default app.
        exists = self.retriever.preference_exists(key)
        match = self.retriever.resolve_preference(key, consume=False, min_confidence=AUTO_EXECUTE_THRESHOLD)
        if match is None:
            if exists:
                return InterpretationResult(False, intent, reason=MatchReason.UNAVAILABLE_COMMAND, confidence=intent.confidence)
            target = self.FALLBACK_TARGETS[key]
            resolved = replace(intent, target=target)
            return self.command_resolver.resolve(resolved, commands)
        value = match.value
        if (match.sensitive or not isinstance(value, str)
                or not AUTO_EXECUTE_THRESHOLD <= match.confidence <= 1.0
                or len(value) > 200 or any(ord(character) < 32 for character in value)):
            return InterpretationResult(False, intent, reason=MatchReason.UNAVAILABLE_COMMAND, confidence=intent.confidence)
        normalized = ' '.join(value.casefold().split())
        # IDs and aliases come solely from the current approved application registry.
        allowed = set(WindowsLauncher.SUPPORTED_APPS) | set(application_aliases)
        direct = {normalized} if normalized in allowed else set()
        aliased = {target for target, aliases in application_aliases.items()
                   if target in allowed and normalized in {' '.join(alias.casefold().split()) for alias in aliases}}
        candidates = direct | aliased
        if len(candidates) != 1:
            reason = MatchReason.AMBIGUOUS_TARGET if candidates else MatchReason.UNSUPPORTED_TARGET
            return InterpretationResult(False, intent, reason=reason, confidence=intent.confidence)
        resolved = replace(intent, target=candidates.pop(), confidence=min(intent.confidence, match.confidence))
        result = self.command_resolver.resolve(resolved, commands)
        if result.matched:
            result = replace(result, memory_id=match.memory_id)
            if consume:
                # Consumption is opt-in; interpretation and tester previews stay read-only.
                if self.retriever.consume(match.memory_id) is None:
                    return InterpretationResult(False, intent, reason=MatchReason.UNAVAILABLE_COMMAND, confidence=intent.confidence)
        return result
