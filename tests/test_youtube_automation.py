"""Unit tests for YouTubeAutomationService with ad-skipping and fallback logic."""
from unittest.mock import MagicMock, patch
import pytest
from src.services.youtube_automation import YouTubeAutomationService


class DummyElement:
    def __init__(self, tag_name="ytd-video-renderer", text="", badges=None):
        self.tag_name = tag_name
        self.text = text
        self._badges = badges or []

    def find_elements(self, by, selector):
        return self._badges


def test_is_ad_element_tags():
    ad_slot = DummyElement(tag_name="ytd-ad-slot-renderer")
    assert YouTubeAutomationService.is_ad_element(ad_slot) is True

    promoted = DummyElement(tag_name="ytd-promoted-video-renderer")
    assert YouTubeAutomationService.is_ad_element(promoted) is True

    normal = DummyElement(tag_name="ytd-video-renderer", text="Ed Sheeran - Shape of You")
    assert YouTubeAutomationService.is_ad_element(normal) is False


def test_is_ad_element_text():
    sponsored_item = DummyElement(tag_name="div", text="Sponsored\nBuy now!")
    assert YouTubeAutomationService.is_ad_element(sponsored_item) is True

    ad_item = DummyElement(tag_name="div", text="Ad\nDiscounted offer")
    assert YouTubeAutomationService.is_ad_element(ad_item) is True

    normal_item = DummyElement(tag_name="div", text="Queen - Bohemian Rhapsody (Official Video)")
    assert YouTubeAutomationService.is_ad_element(normal_item) is False


def test_is_ad_element_badges():
    badge_mock = MagicMock()
    badged_item = DummyElement(tag_name="ytd-video-renderer", badges=[badge_mock])
    assert YouTubeAutomationService.is_ad_element(badged_item) is True


def test_play_song_empty():
    success, msg = YouTubeAutomationService.play_song("   ")
    assert success is False
    assert "Please specify a song name" in msg


@patch.object(YouTubeAutomationService, "_create_webdriver")
def test_play_song_skips_ad_and_clicks_original(mock_create_driver):
    mock_driver = MagicMock()
    mock_create_driver.return_value = mock_driver

    # Candidate 1: Ad
    ad_elem = MagicMock()
    ad_elem.tag_name = "ytd-ad-slot-renderer"
    ad_elem.text = "Sponsored"
    ad_elem.find_elements.return_value = [MagicMock()]

    # Candidate 2: Original Video
    video_elem = MagicMock()
    video_elem.tag_name = "ytd-video-renderer"
    video_elem.text = "Ed Sheeran - Shape of You (Official Music Video)"
    video_elem.find_elements.side_effect = lambda by, selector: (
        [] if selector != "a#video-title" else [title_link]
    )

    title_link = MagicMock()
    title_link.is_displayed.return_value = True
    title_link.get_attribute.side_effect = lambda attr: "Shape of You" if attr == "title" else "https://www.youtube.com/watch?v=JGwWNGJdvx8"

    mock_driver.find_elements.return_value = [ad_elem, video_elem]

    with patch("selenium.webdriver.support.ui.WebDriverWait.until"):
        success, msg = YouTubeAutomationService.play_song("shape of you")

    assert success is True
    assert "Playing 'shape of you' on YouTube..." in msg
    # Ad element must not have its title clicked
    title_link.click.assert_called_once()


@patch.object(YouTubeAutomationService, "_create_webdriver", return_value=None)
@patch("webbrowser.open")
def test_play_song_fallback_when_no_driver(mock_browser, mock_driver):
    mock_browser.return_value = True
    success, msg = YouTubeAutomationService.play_song("believer")
    assert success is True
    mock_browser.assert_called_once()
    assert "believer" in mock_browser.call_args[0][0] or "youtube.com" in mock_browser.call_args[0][0]
