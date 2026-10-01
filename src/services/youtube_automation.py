"""YouTube music playback service for desktop companion.

Features:
- Opens songs directly in the user's EXISTING default browser (as a new tab).
- Automatically finds the top organic/original song video, skipping advertisements and sponsored slots.
- No separate automation browser or test profiles.
- Optional Selenium automation mode retained for automated environments.
"""
import re
import urllib.parse
import urllib.request
import webbrowser
from typing import Tuple, Optional
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("youtube_automation")


class YouTubeAutomationService:
    """Manages YouTube song search and playback."""

    @staticmethod
    def resolve_original_video_id(song_name: str) -> Optional[str]:
        """Queries YouTube search results to extract the first authentic, non-ad video ID.
        
        Filters out 'adSlotRenderer', 'promotedSparklesWebRenderer', and other promotional
        cards by specifically matching genuine 'videoRenderer' entries.
        """
        try:
            encoded = urllib.parse.quote_plus(song_name)
            search_url = f"https://www.youtube.com/results?search_query={encoded}"
            req = urllib.request.Request(
                search_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                # Look specifically for organic videoRenderer entries
                matches = re.findall(r'videoRenderer.*?videoId...([a-zA-Z0-9_-]{11})', html)
                if matches:
                    logger.info(f"Resolved original video ID for '{song_name}': {matches[0]}")
                    return matches[0]
        except Exception as e:
            logger.warning(f"Could not resolve video ID for '{song_name}': {e}")
        return None

    @classmethod
    def play_in_existing_browser(cls, song_name: str) -> Tuple[bool, str]:
        """Plays the song in the user's current, already-opened default browser window."""
        song_name = song_name.strip()
        if not song_name:
            return False, "Please specify a song name."

        video_id = cls.resolve_original_video_id(song_name)
        if video_id:
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"Opening YouTube video in existing browser: {watch_url}")
            opened = webbrowser.open(watch_url)
            if opened:
                return True, f"Playing '{song_name}' on YouTube..."
            return False, "Could not open browser."

        # Fallback to search query if direct ID resolution failed
        encoded = urllib.parse.quote_plus(song_name)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"
        logger.info(f"Opening YouTube search in existing browser fallback: {search_url}")
        if not webbrowser.open(search_url):
            return False, "Could not open browser."
        return True, f"Searching for '{song_name}' on YouTube..."

    @classmethod
    def play_song(cls, song_name: str, use_selenium: bool = False) -> Tuple[bool, str]:
        """Main entry point: plays song in user's existing browser by default."""
        if not song_name or not song_name.strip():
            return False, "Please specify a song name."

        if use_selenium:
            return cls.play_song_with_selenium(song_name)

        return cls.play_in_existing_browser(song_name)

    # --- Optional Selenium automation mode ---

    @staticmethod
    def is_ad_element(element) -> bool:
        """Determines whether a YouTube search result element represents an advertisement."""
        try:
            tag = element.tag_name.lower()
            if "ad-slot" in tag or "promoted" in tag:
                return True

            inner_text = element.text.lower() if element.text else ""
            lines = [line.strip().lower() for line in inner_text.splitlines() if line.strip()]
            for line in lines[:3]:
                if line in ("ad", "sponsored", "promoted"):
                    return True

            ad_badges = element.find_elements("css selector", ".badge-style-type-ad, [aria-label*='Sponsored'], ytd-ad-slot-renderer")
            if ad_badges:
                return True
        except Exception as e:
            logger.debug(f"Error checking ad status on element: {e}")
        return False

    @classmethod
    def _create_webdriver(cls):
        """Attempts to initialize Chrome or Edge WebDriver with detach mode."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.edge.options import Options as EdgeOptions

        try:
            chrome_opts = ChromeOptions()
            chrome_opts.add_experimental_option("detach", True)
            chrome_opts.add_argument("--start-maximized")
            chrome_opts.add_argument("--disable-notifications")
            chrome_opts.add_argument("--log-level=3")
            return webdriver.Chrome(options=chrome_opts)
        except Exception as e:
            logger.warning(f"Could not initialize Chrome WebDriver: {e}. Trying Edge...")

        try:
            edge_opts = EdgeOptions()
            edge_opts.add_experimental_option("detach", True)
            edge_opts.add_argument("--start-maximized")
            edge_opts.add_argument("--disable-notifications")
            edge_opts.add_argument("--log-level=3")
            return webdriver.Edge(options=edge_opts)
        except Exception as e:
            logger.warning(f"Could not initialize Edge WebDriver: {e}")

        return None

    @classmethod
    def play_song_with_selenium(cls, song_name: str) -> Tuple[bool, str]:
        """Automates searching and auto-clicking the first non-ad video using Selenium."""
        song_name = song_name.strip()
        if not song_name:
            return False, "Please specify a song name."

        encoded = urllib.parse.quote_plus(song_name)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            driver = cls._create_webdriver()
            if driver:
                logger.info(f"Navigating to YouTube search: {search_url}")
                driver.get(search_url)

                timeout = settings.YOUTUBE_SELENIUM_TIMEOUT_S
                wait = WebDriverWait(driver, timeout)

                wait.until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "ytd-video-renderer, ytd-ad-slot-renderer, ytd-promoted-video-renderer",
                    ))
                )

                candidates = driver.find_elements(
                    By.CSS_SELECTOR,
                    "ytd-video-renderer, ytd-ad-slot-renderer, ytd-promoted-video-renderer",
                )

                chosen_video = None
                for candidate in candidates:
                    if cls.is_ad_element(candidate):
                        logger.info("Detected advertisement slot in search results, skipping...")
                        continue

                    title_links = candidate.find_elements(By.CSS_SELECTOR, "a#video-title")
                    if title_links and title_links[0].is_displayed():
                        chosen_video = title_links[0]
                        break

                if chosen_video:
                    video_title = chosen_video.get_attribute("title") or song_name
                    video_href = chosen_video.get_attribute("href")
                    logger.info(f"Auto-clicking original video: '{video_title}' ({video_href})")

                    try:
                        chosen_video.click()
                    except Exception:
                        if video_href:
                            driver.get(video_href)
                        else:
                            driver.execute_script("arguments[0].click();", chosen_video)

                    return True, f"Playing '{song_name}' on YouTube..."
        except Exception as e:
            logger.warning(f"Selenium playback failed: {e}. Falling back to existing browser.")

        return cls.play_in_existing_browser(song_name)
