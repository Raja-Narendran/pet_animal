"""Command input box widget with submit button, voice input, and enter-key triggering."""
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QBrush, QPen
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QTimer
from .voice_button import VoiceButton
from ..services.voice_input import VoiceInputWorker, SPEECH_AVAILABLE
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger("command_box")


class CommandBoxWidget(QWidget):
    """Compact desktop command box.
    
    Features:
    - Text input with placeholder.
    - Submit via Enter key or Send button.
    - Automatic input clearing after submission.
    - Modern semi-transparent glass styling.
    
    Note: Uses manual paintEvent instead of QGraphicsDropShadowEffect
    because drop shadow effects cause ghost-rendering artifacts on
    transparent frameless windows (WA_TranslucentBackground).
    """

    command_submitted = pyqtSignal(str)
    voice_started = pyqtSignal()
    voice_error = pyqtSignal(str)

    # Visual constants
    BORDER_RADIUS = 20
    SHADOW_OFFSET_Y = 4
    SHADOW_PADDING = 8  # Extra space around the box for the painted shadow

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setFixedHeight(44 + self.SHADOW_PADDING * 2)
        self.setMinimumWidth(260 + self.SHADOW_PADDING * 2)
        self.setMaximumWidth(320 + self.SHADOW_PADDING * 2)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            10 + self.SHADOW_PADDING,
            4 + self.SHADOW_PADDING,
            6 + self.SHADOW_PADDING,
            4 + self.SHADOW_PADDING,
        )
        layout.setSpacing(6)

        # Text input
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Ask me anything... (e.g. search python, play song)")
        self.input_field.returnPressed.connect(self._handle_submit)
        
        font = QFont("Segoe UI", 10)
        self.input_field.setFont(font)
        
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #ffffff;
                padding: 4px;
                selection-background-color: #3b82f6;
            }
            QLineEdit::placeholder {
                color: #94a3b8;
                font-style: italic;
            }
        """)

        # Voice input button
        self.voice_button = VoiceButton(self)
        if not SPEECH_AVAILABLE:
            self.voice_button.set_unavailable()
        else:
            self.voice_button.voice_toggled.connect(self._start_voice_input)

        # Voice input worker (lazy-initialized on first use)
        self._voice_worker: Optional[VoiceInputWorker] = None

        # Send button
        self.send_button = QPushButton("➤", self)
        self.send_button.setFixedSize(32, 32)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setToolTip("Execute command")
        self.send_button.clicked.connect(self._handle_submit)
        
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: #ffffff;
                border: none;
                border-radius: 16px;
                font-size: 13px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)

        layout.addWidget(self.input_field)
        layout.addWidget(self.voice_button)
        self.voice_button.setVisible(settings.VOICE_ENABLED)
        layout.addWidget(self.send_button)

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

        # Draw subtle shadow (slightly offset, larger, semi-transparent)
        shadow_rect = box_rect.adjusted(-2, 0, 2, self.SHADOW_OFFSET_Y)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 60))

        # Draw main background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(box_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)
        color = QColor(getattr(self, "background_color", "#18181b"))
        color.setAlphaF(getattr(self, "background_opacity", 240 / 255))
        painter.fillPath(bg_path, color)

        # Draw border
        painter.setPen(QPen(QColor(255, 255, 255, 46), 1.0))
        painter.drawRoundedRect(box_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)

        painter.end()

    def _handle_submit(self) -> None:
        """Processes and emits the command."""
        text = self.input_field.text().strip()
        logger.debug("Command submitted")
        self.command_submitted.emit(text)
        self.input_field.clear()

    def focus_input(self) -> None:
        """Sets focus to the input field."""
        self.input_field.setFocus()
        self.input_field.selectAll()

    # --- Voice input handlers ---

    def _start_voice_input(self) -> None:
        """Launches the background voice recognition worker."""
        if not settings.VOICE_ENABLED:
            return
        if self._voice_worker and self._voice_worker.isRunning():
            logger.debug("Voice worker already running, ignoring.")
            return

        self._voice_worker = VoiceInputWorker(parent=self)
        self._voice_worker.listening_started.connect(self._on_voice_listening)
        self._voice_worker.speech_recognized.connect(self._on_voice_recognized)
        self._voice_worker.error_occurred.connect(self._on_voice_error)
        self._voice_worker.listening_stopped.connect(self._on_voice_stopped)
        self._voice_worker.start()

    def _on_voice_listening(self) -> None:
        """Called when the mic starts capturing."""
        self.voice_button.set_listening()
        self.input_field.setPlaceholderText("🎤  Listening...")
        self.voice_started.emit()

    def _on_voice_recognized(self, text: str) -> None:
        """Called when speech is successfully transcribed."""
        logger.info(f"Voice recognized, submitting: '{text}'")
        # Show the recognized text briefly in the input field, then submit
        self.input_field.setText(text)
        self.command_submitted.emit(text)
        self.input_field.clear()

    def _on_voice_error(self, error_msg: str) -> None:
        """Called when voice recognition fails."""
        logger.warning(f"Voice input error: {error_msg}")
        # Briefly show error in placeholder, restore after 3 seconds
        self.input_field.setPlaceholderText(f"⚠ {error_msg}")
        self.voice_error.emit(error_msg)
        QTimer.singleShot(3000, self._restore_placeholder)

    def _on_voice_stopped(self) -> None:
        """Called when the voice worker finishes (success or failure)."""
        self.voice_button.set_idle()

    def _restore_placeholder(self) -> None:
        """Restores the default placeholder text."""
        self.input_field.setPlaceholderText("Ask me anything... (e.g. search python, play song)")

