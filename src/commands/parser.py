"""Command parsing layer.

Designed to allow seamless drop-in of future AI / Natural Language parsers
without altering the Command model or Executor.
"""
import re
from abc import ABC, abstractmethod
from .model import Command, ActionType
from .interpreter.patterns import APPLICATION_ALIASES, SEARCH_PREFIXES, MUSIC_PREFIXES, HELP_PHRASES, music_request
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("parser")


class BaseCommandParser(ABC):
    """Abstract interface for parsing raw user input into normalized Commands."""

    @abstractmethod
    def parse(self, text: str) -> Command:
        """Parse raw input string into a structured Command."""
        pass


class RuleBasedCommandParser(BaseCommandParser):
    """Deterministic, rule-based command parser for V1 desktop companion.
    
    Normalizes whitespace and casing, strips common verbs ('open', 'launch', 'start', 'run'),
    and maps only to strictly predefined application and URL targets.
    """

    # Verbs that can prefix an action
    ACTION_PREFIXES = ("open", "launch", "start", "run")

    # Target synonyms to normalized target keys
    APP_TARGET_MAP = {alias: target for target, aliases in APPLICATION_ALIASES.items() for alias in aliases}
    URL_TARGET_MAP = settings.SUPPORTED_URLS
    HELP_TRIGGERS = HELP_PHRASES

    def parse(self, text: str) -> Command:
        """Parses user input into a Command."""
        if not text or not text.strip():
            logger.debug("Received empty command input.")
            return Command(action=ActionType.EMPTY, raw_input=text or "")

        # 1. Normalize: lowercase, trim, collapse consecutive whitespaces
        cleaned = re.sub(r"\s+", " ", text.strip().lower())
        logger.debug('Parsing command input.')

        # 2. Check for help triggers
        if cleaned in self.HELP_TRIGGERS:
            return Command(action=ActionType.SHOW_HELP, raw_input=text)

        # 3. Check for web search triggers
        search_prefixes = tuple(prefix + ' ' for prefix in SEARCH_PREFIXES)
        if cleaned in ("search", "search for", "look up", "find"):
            logger.info("Resolved to empty SEARCH_WEB command.")
            return Command(action=ActionType.SEARCH_WEB, target="", raw_input=text)

        for s_prefix in search_prefixes:
            if cleaned.startswith(s_prefix):
                search_query = cleaned[len(s_prefix):].strip()
                if search_query:
                    logger.info('Resolved to SEARCH_WEB.')
                    return Command(
                        action=ActionType.SEARCH_WEB,
                        target=search_query,
                        raw_input=text,
                    )

        music = music_request(cleaned)
        if music is not None:
            provider, song = music
            return Command(action=ActionType.PLAY_MUSIC, target=song, raw_input=text,
                           parameters={'provider': provider} if provider else {})

        # 5. Check for verb prefixes (e.g., 'open chrome', 'launch notepad')
        target_candidate = cleaned
        has_verb_prefix = False

        for prefix in self.ACTION_PREFIXES:
            if cleaned == prefix:
                # User typed just "open" or "launch" without a target
                return Command(action=ActionType.UNKNOWN, raw_input=text)
            if cleaned.startswith(prefix + " "):
                target_candidate = cleaned[len(prefix) + 1:].strip()
                has_verb_prefix = True
                break

        # 6. Check if target candidate matches supported apps
        if target_candidate in self.APP_TARGET_MAP:
            normalized_app = self.APP_TARGET_MAP[target_candidate]
            logger.info(f"Resolved to OPEN_APPLICATION: {normalized_app}")
            return Command(
                action=ActionType.OPEN_APPLICATION,
                target=normalized_app,
                raw_input=text,
            )

        # 7. Check if target candidate matches supported URLs
        if target_candidate in self.URL_TARGET_MAP:
            target_url = self.URL_TARGET_MAP[target_candidate]
            logger.info(f"Resolved to OPEN_URL: {target_url}")
            return Command(
                action=ActionType.OPEN_URL,
                target=target_url,
                raw_input=text,
            )

        # 6. Unrecognized or unsupported target
        logger.info('Unrecognized command.')
        return Command(
            action=ActionType.UNKNOWN,
            target=target_candidate,
            raw_input=text,
        )
