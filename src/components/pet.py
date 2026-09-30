"""Pet display widget with animation, drag support, and click interaction."""
from typing import Optional, List
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPixmap, QMouseEvent, QCursor
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint
from ..utils.sprite import SpriteManager
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("pet_widget")


class PetWidget(QWidget):
    """Interactive floating pet widget.
    
    Handles:
    - Frame-by-frame sprite sheet animation.
    - Dragging the parent window smoothly without misinterpreting drags as clicks.
    - Emitting click signal to toggle the command box.
    - State transitions (idle, thinking, working, success, error, greeting).
    """

    pet_clicked = pyqtSignal()
    drag_finished = pyqtSignal(QPoint)

    # Pixel threshold to differentiate dragging from clicking
    DRAG_THRESHOLD_PIXELS = 6

    def __init__(self, sprite_manager: Optional[SpriteManager] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.sprite_manager = sprite_manager or SpriteManager(settings.PET_WIDTH, settings.PET_HEIGHT)
        
        self.current_state = "idle"
        self.current_frame_idx = 0
        self.frames: List[QPixmap] = self.sprite_manager.get_frames(self.current_state)

        self.setFixedSize(settings.PET_WIDTH, settings.PET_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Dragging state
        self._press_pos: Optional[QPoint] = None
        self._window_press_pos: Optional[QPoint] = None
        self._is_dragging = False

        # Animation timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._advance_frame)
        self.anim_timer.start(settings.ANIMATION_INTERVAL_MS)

        # Temporary state timer (e.g., return to idle after success/error)
        self.temp_state_timer = QTimer(self)
        self.temp_state_timer.setSingleShot(True)
        self.temp_state_timer.timeout.connect(self._revert_to_idle)

    def set_state(self, state: str, temporary_ms: Optional[int] = None) -> None:
        """Sets the pet animation state (e.g., 'idle', 'working', 'success', 'error')."""
        if self.temp_state_timer.isActive():
            self.temp_state_timer.stop()

        self.current_state = state
        self.frames = self.sprite_manager.get_frames(state)
        self.current_frame_idx = 0
        self.update()
        logger.debug(f"Pet state changed to '{state}' (frames: {len(self.frames)})")

        if temporary_ms and temporary_ms > 0 and state != "idle":
            self.temp_state_timer.start(temporary_ms)

    def _revert_to_idle(self) -> None:
        """Reverts pet state back to idle."""
        self.set_state("idle")

    def _advance_frame(self) -> None:
        """Advances to the next sprite frame."""
        if not self.frames:
            return
        self.current_frame_idx = (self.current_frame_idx + 1) % len(self.frames)
        self.update()

    def paintEvent(self, event: "QPaintEvent") -> None:
        """Draws the current frame centered."""
        if not self.frames:
            return
        painter = QPainter(self)
        frame = self.frames[self.current_frame_idx]
        
        # Center the frame within the widget
        x = (self.width() - frame.width()) // 2
        y = (self.height() - frame.height()) // 2
        painter.drawPixmap(x, y, frame)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Tracks the start of a mouse click/drag."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            win = self.window()
            if win:
                self._window_press_pos = win.pos()
            self._is_dragging = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Drags the window if the movement exceeds the drag threshold."""
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_pos and self._window_press_pos:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self._press_pos
            
            if not self._is_dragging and delta.manhattanLength() > self.DRAG_THRESHOLD_PIXELS:
                self._is_dragging = True

            if self._is_dragging:
                win = self.window()
                if win:
                    win.move(self._window_press_pos + delta)
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Emits clicked signal if not dragged, or drag_finished if dragged."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_dragging:
                logger.debug("Pet clicked: toggling command box")
                self.pet_clicked.emit()
            else:
                win = self.window()
                if win:
                    self.drag_finished.emit(win.pos())
            
            self._is_dragging = False
            self._press_pos = None
            self._window_press_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)
