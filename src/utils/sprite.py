"""Sprite sheet slicing and animation frame manager."""
import os
from typing import Dict, List
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QRect
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("sprite")


class SpriteManager:
    """Manages loading and frame extraction for pet sprite sheets."""

    def __init__(self, target_width: int = settings.PET_WIDTH, target_height: int = settings.PET_HEIGHT):
        self.target_width = target_width
        self.target_height = target_height
        self._cache: Dict[str, List[QPixmap]] = {}
        self._load_all_states()

    def _load_all_states(self) -> None:
        """Loads and prepares frames for all configured pet states."""
        for state_name, file_name in settings.PET_STATES.items():
            image_path = settings.PET_IMAGE_DIR / file_name
            frames = self._slice_sprite_sheet(str(image_path))
            if frames:
                self._cache[state_name] = frames
                logger.info(f"Loaded {len(frames)} frames for pet state '{state_name}' from {file_name}")
            else:
                logger.warning(f"Could not load frames for state '{state_name}' ({file_name})")

        # Ensure default 'idle' state exists
        if "idle" not in self._cache:
            logger.warning("No 'idle' state loaded! Creating a fallback pixmap.")
            self._cache["idle"] = [self._create_fallback_pixmap()]

    def _slice_sprite_sheet(self, filepath: str) -> List[QPixmap]:
        """Loads a horizontal sprite sheet PNG and slices it into uniform square frames."""
        if not os.path.exists(filepath):
            logger.error(f"Sprite image file does not exist: {filepath}")
            return []

        sheet = QPixmap(filepath)
        if sheet.isNull():
            logger.error(f"Failed to load QPixmap from {filepath}")
            return []

        sheet_w = sheet.width()
        sheet_h = sheet.height()

        if sheet_h <= 0 or sheet_w <= 0:
            return []

        # Determine frame size (square frames where frame_w = sheet_h)
        frame_size = sheet_h
        num_frames = sheet_w // frame_size

        if num_frames == 0:
            num_frames = 1
            frame_size = sheet_w

        frames: List[QPixmap] = []
        for i in range(num_frames):
            frame_rect = QRect(i * frame_size, 0, frame_size, frame_size)
            frame_pixmap = sheet.copy(frame_rect)
            
            # Scale frame crisp using FastTransformation (nearest neighbor) to preserve pixel art
            scaled_frame = frame_pixmap.scaled(
                self.target_width,
                self.target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            frames.append(scaled_frame)

        return frames

    def _create_fallback_pixmap(self) -> QPixmap:
        """Creates a simple colored pixmap in case no assets are found."""
        pix = QPixmap(self.target_width, self.target_height)
        pix.fill(Qt.GlobalColor.transparent)
        return pix

    def get_frames(self, state: str) -> List[QPixmap]:
        """Returns the list of frames for a requested state, or falls back to 'idle'."""
        if state in self._cache and self._cache[state]:
            return self._cache[state]
        return self._cache.get("idle", [self._create_fallback_pixmap()])
