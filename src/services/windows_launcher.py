"""Safe Windows application launcher service.

Security guarantee:
- Only executes registered, predefined applications from an explicit whitelist.
- Never passes raw user input to a shell.
- Validates all URLs against allowed HTTPS targets.
"""
import os
import shutil
import subprocess
import urllib.parse
import webbrowser
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("launcher")


class BaseLauncher(ABC):
    """Abstract interface for desktop launcher (enables easy testing and mocking)."""

    @abstractmethod
    def open_application(self, app_key: str) -> Tuple[bool, str]:
        """Launch a registered application by its normalized key."""
        pass

    @abstractmethod
    def open_url(self, url: str) -> Tuple[bool, str]:
        """Open a URL in the user's default browser."""
        pass

    def search_web(self, query: str) -> Tuple[bool, str]:
        """Search the web using default browser and search engine."""
        return False, "Not implemented"

    def play_youtube(self, song_name: str) -> Tuple[bool, str]:
        """Search and play a song on YouTube."""
        return False, "Not implemented"


class WindowsLauncher(BaseLauncher):
    """Safe Windows launcher implementation."""

    # Whitelist of allowed application targets
    SUPPORTED_APPS = {"chrome", "notepad", "calculator", "explorer", "vscode"}

    def __init__(self):
        self._vscode_path: Optional[str] = None
        self._chrome_path: Optional[str] = None

    def find_vscode(self) -> Optional[str]:
        """Locates VS Code executable via PATH or standard installation directories."""
        if self._vscode_path and os.path.exists(self._vscode_path):
            return self._vscode_path

        # 1. Check PATH for code or code.cmd
        which_code = shutil.which("code") or shutil.which("code.cmd")
        if which_code:
            self._vscode_path = which_code
            return self._vscode_path

        # 2. Check standard installation directories
        for candidate in settings.VSCODE_PATHS:
            if candidate and os.path.isfile(candidate):
                self._vscode_path = candidate
                return self._vscode_path

        return None

    def find_chrome(self) -> Optional[str]:
        """Locates Chrome executable via PATH or standard installation directories."""
        if self._chrome_path and os.path.exists(self._chrome_path):
            return self._chrome_path

        # 1. Check PATH
        which_chrome = shutil.which("chrome") or shutil.which("chrome.exe")
        if which_chrome:
            self._chrome_path = which_chrome
            return self._chrome_path

        # 2. Check standard installation directories
        for candidate in settings.CHROME_PATHS:
            if candidate and os.path.isfile(candidate):
                self._chrome_path = candidate
                return self._chrome_path

        return None

    def open_application(self, app_key: str) -> Tuple[bool, str]:
        """Launches a whitelisted application safely."""
        app_key = app_key.lower().strip()

        if app_key not in self.SUPPORTED_APPS:
            logger.warning(f"Rejected unsupported application key: {app_key}")
            return False, f"I don't know how to open '{app_key}'."

        try:
            if app_key == "notepad":
                logger.info("Launching Notepad...")
                subprocess.Popen(["notepad.exe"])
                return True, "Opening Notepad..."

            elif app_key == "calculator":
                logger.info("Launching Calculator...")
                subprocess.Popen(["calc.exe"])
                return True, "Opening Calculator..."

            elif app_key == "explorer":
                logger.info("Launching File Explorer...")
                subprocess.Popen(["explorer.exe"])
                return True, "Opening File Explorer..."

            elif app_key == "chrome":
                logger.info("Launching Chrome...")
                chrome_exe = self.find_chrome()
                if chrome_exe:
                    subprocess.Popen([chrome_exe])
                    return True, "Opening Chrome..."
                
                # Try generic launch via Windows App Paths registry
                try:
                    subprocess.Popen(["chrome.exe"])
                    return True, "Opening Chrome..."
                except (FileNotFoundError, OSError):
                    logger.error("Chrome executable not found on system.")
                    return False, "I couldn't find Google Chrome on this computer."

            elif app_key == "vscode":
                logger.info("Launching VS Code...")
                vscode_path = self.find_vscode()
                if vscode_path:
                    # Validate the resolved path actually exists on disk
                    if not os.path.isfile(vscode_path):
                        logger.error(f"Resolved VS Code path does not exist: {vscode_path}")
                        return False, "I couldn't find Visual Studio Code on this computer."
                    if vscode_path.lower().endswith((".cmd", ".bat")):
                        # Launch .cmd/.bat via cmd.exe without shell=True to avoid
                        # shell injection. subprocess list form with cmd /c is safe
                        # because vscode_path comes from our own resolution, not user input.
                        subprocess.Popen(["cmd", "/c", vscode_path])
                    else:
                        subprocess.Popen([vscode_path])
                    return True, "Opening Visual Studio Code..."
                else:
                    logger.error("VS Code not found in PATH or standard directories.")
                    return False, "I couldn't find Visual Studio Code on this computer."

        except Exception as e:
            logger.exception(f"Failed to launch application '{app_key}': {e}")
            return False, f"Failed to open {app_key}: {e}"

        return False, f"Unsupported application: {app_key}"

    def open_url(self, url: str) -> Tuple[bool, str]:
        """Opens a validated URL using the default browser."""
        if not url.startswith("https://"):
            logger.warning(f"Rejected invalid URL scheme: {url}")
            return False, "Invalid URL scheme."

        if url not in settings.SUPPORTED_URLS.values():
            logger.warning(f"Rejected unsupported URL: {url}")
            return False, "This website is not supported."

        friendly_name = "website"
        if "youtube.com" in url:
            friendly_name = "YouTube"
        elif "google.com" in url:
            friendly_name = "Google"

        try:
            logger.info(f"Opening URL in default browser: {url}")
            # webbrowser.open opens in the system's default browser safely
            opened = webbrowser.open(url)
            if opened:
                return True, f"Opening {friendly_name}..."
            else:
                return False, f"Could not launch browser for {friendly_name}."
        except Exception as e:
            logger.exception(f"Error opening URL {url}: {e}")
            return False, f"Failed to open {friendly_name}: {e}"

    def search_web(self, query: str) -> Tuple[bool, str]:
        """Opens default browser and searches the query using Google."""
        query = query.strip()
        if not query:
            return False, "Please specify a search query."

        try:
            encoded_query = urllib.parse.quote_plus(query)
            search_url = settings.DEFAULT_SEARCH_ENGINE_URL.format(query=encoded_query)
            logger.info(f"Opening Google search in default browser: {search_url}")
            opened = webbrowser.open(search_url)
            if opened:
                return True, f"Searching for '{query}' on Google..."
            return False, "Could not open browser for web search."
        except Exception as e:
            logger.exception(f"Error executing web search for '{query}': {e}")
            return False, f"Failed to search: {e}"

    def play_youtube(self, song_name: str) -> Tuple[bool, str]:
        """Automates searching and playing the song on YouTube, skipping ads."""
        from .youtube_automation import YouTubeAutomationService
        return YouTubeAutomationService.play_song(song_name)
