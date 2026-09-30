"""YouTube browser automation service using Selenium with ad-skipping logic.

Provides:
- Automated YouTube search and auto-click of the first genuine video.
- Explicit detection and skipping of advertisements and sponsored slots.
- Persistent browser playback (detach=True) so the song keeps playing.
- Resilient fallback to default browser URL opening if WebDriver is unavailable.
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
    """Automates YouTube playback in a real browser, skipping ads."""

    @staticmethod
    def is_ad_element(element) -> bool:
        """Determines whether a YouTube search result element represents an advertisement."""
        try:
            tag = element.tag_name.lower()
            if "ad-slot" in tag or "promoted" in tag:
                return True

            # Check inner HTML / text for ad indicators
            inner_text = element.text.lower() if element.text else ""
            lines = [line.strip().lower() for line in inner_text.splitlines() if line.strip()]
            for line in lines[:3]:  # Ads typically show 'Sponsored' or 'Ad' at the very top
                if line in ("ad", "sponsored", "promoted"):
                    return True

            # Check for ad badge classes or attributes
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

        # 1. Try Chrome first
        try:
            chrome_opts = ChromeOptions()
            chrome_opts.add_experimental_option("detach", True)
            chrome_opts.add_argument("--start-maximized")
            chrome_opts.add_argument("--disable-notifications")
            chrome_opts.add_argument("--log-level=3")
            driver = webdriver.Chrome(options=chrome_opts)
            logger.info("Initialized Chrome WebDriver.")
            return driver
        except Exception as e:
            logger.warning(f"Could not initialize Chrome WebDriver: {e}. Trying Edge...")

        # 2. Try Edge as secondary
        try:
            edge_opts = EdgeOptions()
            edge_opts.add_experimental_option("detach", True)
            edge_opts.add_argument("--start-maximized")
            edge_opts.add_argument("--disable-notifications")
            edge_opts.add_argument("--log-level=3")
            driver = webdriver.Edge(options=edge_opts)
            logger.info("Initialized Edge WebDriver.")
            return driver
        except Exception as e:
            logger.warning(f"Could not initialize Edge WebDriver: {e}")

        return None

    @classmethod
    def play_song(cls, song_name: str) -> Tuple[bool, str]:
        """Searches for a song on YouTube, skips advertisements, and plays the first original video."""
        song_name = song_name.strip()
        if not song_name:
            return False, "Please specify a song name."

        encoded = urllib.parse.quote_plus(song_name)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"

        # Attempt Selenium automation
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

                # Wait for search results to load
                wait.until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "ytd-video-renderer, ytd-ad-slot-renderer, ytd-promoted-video-renderer",
                    ))
                )

                # Query candidate result containers
                candidates = driver.find_elements(
                    By.CSS_SELECTOR,
                    "ytd-video-renderer, ytd-ad-slot-renderer, ytd-promoted-video-renderer",
                )

                chosen_video = None
                for candidate in candidates:
                    if cls.is_ad_element(candidate):
                        logger.info("Detected advertisement slot in search results, skipping...")
                        continue

                    # Look for video title link
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
                        # Fallback to JavaScript click or direct navigation
                        if video_href:
                            driver.get(video_href)
                        else:
                            driver.execute_script("arguments[0].click();", chosen_video)

                    return True, f"Playing '{song_name}' on YouTube..."
                else:
                    logger.warning("No non-ad video element found to click via Selenium.")
        except Exception as e:
            logger.warning(f"Selenium playback failed: {e}. Falling back to default browser.")

        # Fallback: extract organic video ID or open search in default browser
        return cls._fallback_open(song_name, search_url)

    @classmethod
    def _fallback_open(cls, song_name: str, search_url: str) -> Tuple[bool, str]:
        """Resilient fallback that opens the video or search page in system's default browser."""
        try:
            req = urllib.request.Request(
                search_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                # Look specifically for organic videoRenderer (not adSlotRenderer)
                matches = re.findall(r'videoRenderer.*?"videoId":"([a-zA-Z0-9_-]{11})"', html)
                if matches:
                    watch_url = f"https://www.youtube.com/watch?v={matches[0]}"
                    logger.info(f"Fallback opening organic watch URL: {watch_url}")
                    webbrowser.open(watch_url)
                    return True, f"Playing '{song_name}' on YouTube..."
        except Exception as e:
            logger.warning(f"Could not resolve video ID in fallback: {e}")

        logger.info(f"Fallback opening search results: {search_url}")
        webbrowser.open(search_url)
        return True, f"Searching for '{song_name}' on YouTube..."
