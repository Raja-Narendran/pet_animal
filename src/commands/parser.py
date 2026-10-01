"""Command parsing layer.

Designed to allow seamless drop-in of future AI / Natural Language parsers
without altering the Command model or Executor.
"""
import re
from abc import ABC, abstractmethod
from .model import Command, ActionType
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
    APP_TARGET_MAP = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "notepad": "notepad",
        "calculator": "calculator",
        "calc": "calculator",
        "explorer": "explorer",
        "file explorer": "explorer",
        "windows explorer": "explorer",
        "vscode": "vscode",
        "vs code": "vscode",
        "code": "vscode",
        "visual studio code": "vscode",
    }

    URL_TARGET_MAP = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
    }

    HELP_TRIGGERS = {"help", "commands", "?", "show help", "what can you do"}

    def parse(self, text: str) -> Command:
        """Parses user input into a Command."""
        if not text or not text.strip():
            logger.debug("Received empty command input.")
            return Command(action=ActionType.EMPTY, raw_input=text or "")

        # 1. Normalize: lowercase, trim, collapse consecutive whitespaces
        cleaned = re.sub(r"\s+", " ", text.strip().lower())
        logger.debug(f"Parsing normalized input: '{cleaned}' (raw: '{text}')")

        # 2. Check for help triggers
        if cleaned in self.HELP_TRIGGERS:
            return Command(action=ActionType.SHOW_HELP, raw_input=text)

        # 3. Check for web search triggers
        search_prefixes = (
            "search for ",
            "search on google ",
            "search google for ",
            "search google ",
            "search ",
            "look up ",
            "find ",
            "google ",
        )
        if cleaned in ("search", "search for", "look up", "find"):
            logger.info("Resolved to empty SEARCH_WEB command.")
            return Command(action=ActionType.SEARCH_WEB, target="", raw_input=text)

        for s_prefix in search_prefixes:
            if cleaned.startswith(s_prefix):
                search_query = cleaned[len(s_prefix):].strip()
                if search_query:
                    logger.info(f"Resolved to SEARCH_WEB: '{search_query}'")
                    return Command(
                        action=ActionType.SEARCH_WEB,
                        target=search_query,
                        raw_input=text,
                    )

        # 4. Check for play music / YouTube triggers
        music_prefixes = (
            "play on youtube ",
            "youtube play ",
            "play song ",
            "play music ",
            "play ",
        )
        if cleaned in ("play", "play song", "play music"):
            logger.info("Resolved to empty PLAY_MUSIC command.")
            return Command(action=ActionType.PLAY_MUSIC, target="", raw_input=text)

        for m_prefix in music_prefixes:
            if cleaned.startswith(m_prefix):
                song_candidate = cleaned[len(m_prefix):].strip()
                if song_candidate.endswith(" on youtube"):
                    song_candidate = song_candidate[:-11].strip()
                if song_candidate:
                    logger.info(f"Resolved to PLAY_MUSIC: '{song_candidate}'")
                    return Command(
                        action=ActionType.PLAY_MUSIC,
                        target=song_candidate,
                        raw_input=text,
                    )

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
        logger.info(f"Unrecognized command: '{text}' (candidate: '{target_candidate}')")
        return Command(
            action=ActionType.UNKNOWN,
            target=target_candidate,
            raw_input=text,
        )
