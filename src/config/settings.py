"""Application configuration and settings."""
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


@dataclass
class Settings:
    """Configuration settings for Pet Animal."""
    
    # Application Info
    APP_NAME: str = "Pet Animal"
    APP_ID: str = "com.petanimal.desktop"
    VERSION: str = "1.0.0"
    
    # Paths
    BASE_DIR: Path = field(default_factory=_get_base_dir)
    PET_IMAGE_DIR: Path = field(default_factory=lambda: _get_base_dir() / "petimage")
    STATE_FILE: Path = field(default_factory=lambda: Path.home() / ".pet_animal" / "state.json")
    LOG_FILE: Path = field(default_factory=lambda: Path.home() / ".pet_animal" / "pet_animal.log")
    
    # Window & Display
    PET_WIDTH: int = 240
    PET_HEIGHT: int = 240
    SPRITE_FRAME_SIZE: int = 64
    ANIMATION_INTERVAL_MS: int = 180
    ALWAYS_ON_TOP: bool = True
    BUBBLE_TIMEOUT_MS: int = 6000

    # Voice Input
    VOICE_ENABLED: bool = True          # Master switch for voice input feature
    VOICE_TIMEOUT_S: int = 5            # Seconds to wait for speech to start
    VOICE_PHRASE_LIMIT_S: int = 10      # Max seconds for a single spoken phrase
    VOICE_NETWORK_TIMEOUT_S: int = 10   # Timeout for speech recognition requests
    
    # Sprite State Mapping
    PET_STATES: Dict[str, str] = field(default_factory=lambda: {
        "idle": "husky-idle.png",
        "greeting": "husky-greeting.png",
        "thinking": "husky-thinking.png",
        "working": "husky-working.png",
        "success": "husky-success.png",
        "error": "husky-error.png",
        "sleeping": "husky-sleeping.png",
    })
    
    # Known Safe URLs
    SUPPORTED_URLS: Dict[str, str] = field(default_factory=lambda: {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
    })
    
    # Search & YouTube Playback Settings
    DEFAULT_SEARCH_ENGINE_URL: str = "https://www.google.com/search?q={query}"
    YOUTUBE_SEARCH_URL: str = "https://www.youtube.com/results?search_query={query}"
    YOUTUBE_WATCH_URL: str = "https://www.youtube.com/watch?v={video_id}"
    YOUTUBE_SELENIUM_TIMEOUT_S: int = 10
    
    # Common Windows executable paths for fallback search
    VSCODE_PATHS: List[str] = field(default_factory=lambda: [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Microsoft VS Code\Code.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft VS Code\Code.exe"),
    ])
    
    CHROME_PATHS: List[str] = field(default_factory=lambda: [
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ])


# Global singleton instance
settings = Settings()
