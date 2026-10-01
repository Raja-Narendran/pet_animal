"""Unit tests for SpriteManager and asset loading."""
import pytest
import os
from PyQt6.QtWidgets import QApplication
from src.utils.sprite import SpriteManager


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication instance exists for QPixmap operations."""
    app = QApplication.instance()
    if app is None:
        # Offscreen platform for headless execution
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication([])
    return app


def test_sprite_manager_loads_states(qapp):
    sm = SpriteManager(target_width=128, target_height=128)
    
    # Check that idle exists
    idle_frames = sm.get_frames("idle")
    assert len(idle_frames) == 4
    for f in idle_frames:
        assert not f.isNull()
        assert f.width() == 128
        assert f.height() == 128


def test_sprite_manager_all_states(qapp):
    sm = SpriteManager(target_width=64, target_height=64)
    expected_frames = {
        "idle": 4,
        "greeting": 6,
        "thinking": 6,
        "working": 8,
        "success": 8,
        "error": 4,
        "sleeping": 4,
    }

    for state, count in expected_frames.items():
        frames = sm.get_frames(state)
        assert len(frames) == count, f"State '{state}' expected {count} frames, got {len(frames)}"
        assert not frames[0].isNull()


def test_sprite_manager_missing_state_fallback(qapp):
    sm = SpriteManager(target_width=64, target_height=64)
    fallback_frames = sm.get_frames("nonexistent_state")
    assert len(fallback_frames) >= 1
    assert not fallback_frames[0].isNull()
