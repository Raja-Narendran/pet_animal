"""Resolve metadata against live registered commands, never phrases or OS paths."""
import json
from collections.abc import Mapping, Sequence
from .models import AUTO_EXECUTE_THRESHOLD, CommandIntent, InterpretationResult, IntentType, MatchReason
from ...config.settings import settings


class IntentResolver:
    @staticmethod
    def command_intent(command: Mapping) -> CommandIntent | None:
        target = command.get('target')
        if target is None:
            try:
                target = json.loads(command['action_config'])['target']
            except (KeyError, TypeError, ValueError):
                return None
        if command.get('action_type') == 'routine':
            return CommandIntent(IntentType.RUN_ROUTINE, target)
        if command.get('action_type') == 'application':
            return CommandIntent(IntentType.OPEN_APPLICATION, target)
        if command.get('action_type') == 'url':
            name = next((key for key, url in settings.SUPPORTED_URLS.items() if url == target), target)
            return CommandIntent(IntentType.OPEN_WEBSITE, name)
        return None

    def resolve(self, intent: CommandIntent, commands: Sequence[Mapping]) -> InterpretationResult:
        kind = intent.intent
        # Existing Google/YouTube registrations authorize their browser capabilities.
        # No synthetic registry, SQL migration, paths, or URLs come from interpreted text.
        if kind in (IntentType.WEB_SEARCH, IntentType.PLAY_MEDIA):
            kind = IntentType.OPEN_WEBSITE
        candidates = [command for command in commands
                      if (metadata := self.command_intent(command)) is not None
                      and (metadata.intent, metadata.target) == (kind, intent.target)]
        enabled = [command for command in candidates if command.get('enabled')]
        reason = MatchReason.SMART_MATCH
        command_id = None
        if not candidates:
            reason = MatchReason.UNAVAILABLE_COMMAND
        elif not enabled:
            reason = MatchReason.DISABLED_COMMAND
        elif len(enabled) > 1:
            reason = MatchReason.AMBIGUOUS_COMMAND
        else:
            command_id = enabled[0]['id']
            if not AUTO_EXECUTE_THRESHOLD <= intent.confidence <= 1.0:
                reason = MatchReason.LOW_CONFIDENCE
        return InterpretationResult(reason == MatchReason.SMART_MATCH, intent, command_id, reason, intent.confidence)
