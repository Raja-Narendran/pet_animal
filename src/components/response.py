"""Speech bubble widget for displaying pet command responses."""
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtCore import Qt, QTimer, QRectF
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("response_bubble")


class ResponseBubbleWidget(QWidget):
    """Floating speech/response bubble above the pet.
    
    Note: Uses manual paintEvent instead of QGraphicsDropShadowEffect
    because drop shadow effects cause ghost-rendering artifacts on
    transparent frameless windows (WA_TranslucentBackground).
    """

    BORDER_RADIUS = 12
    SHADOW_OFFSET_Y = 3
    SHADOW_PADDING = 6

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._init_ui()

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.hide)

    def _init_ui(self) -> None:
        self.setMinimumWidth(180 + self.SHADOW_PADDING * 2)
        self.setMaximumWidth(280 + self.SHADOW_PADDING * 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            14 + self.SHADOW_PADDING,
            10 + self.SHADOW_PADDING,
            14 + self.SHADOW_PADDING,
            10 + self.SHADOW_PADDING,
        )
        layout.setSpacing(4)

        self.label = QLabel("", self)
        self.label.setFont(QFont("Segoe UI", 9))
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                color: #f8fafc;
                background: transparent;
                line-height: 1.3;
            }
        """)
        layout.addWidget(self.label)

        self.hide()

    def paintEvent(self, event) -> None:
        """Manually paints the rounded dark background and subtle shadow.
        
        This replaces QGraphicsDropShadowEffect which causes ghost-rendering
        on transparent frameless windows.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pad = self.SHADOW_PADDING
        box_rect = QRectF(
            pad, pad,
            self.width() - pad * 2,
            self.height() - pad * 2,
        )

        # Draw subtle shadow
        shadow_rect = box_rect.adjusted(-1, 0, 1, self.SHADOW_OFFSET_Y)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 55))

        # Draw main background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(box_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)
        painter.fillPath(bg_path, QColor(15, 23, 42, 240))

        # Draw border
        painter.setPen(QPen(QColor(255, 255, 255, 51), 1.0))
        painter.drawRoundedRect(box_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)

        painter.end()

    def show_message(self, message: str, timeout_ms: int = settings.BUBBLE_TIMEOUT_MS) -> None:
        """Displays a message and schedules auto-hiding."""
        self.label.setText(message)
        self.adjustSize()
        self.show()
        logger.debug("Response bubble displayed")

        if self.auto_hide_timer.isActive():
            self.auto_hide_timer.stop()

        if timeout_ms > 0:
            self.auto_hide_timer.start(timeout_ms)
