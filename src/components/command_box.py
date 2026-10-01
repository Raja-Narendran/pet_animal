"""Command input box widget with submit button, voice input, and enter-key triggering."""
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QBrush, QPen, QMouseEvent
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QTimer, QPoint
from .voice_button import VoiceButton
from .audio_waveform import AudioWaveform
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
    voice_command_submitted = pyqtSignal(str)
    voice_started = pyqtSignal()
    voice_error = pyqtSignal(str)
    expand_clicked = pyqtSignal()
    drag_finished = pyqtSignal(QPoint)

    # Visual constants
    BORDER_RADIUS = 20
    SHADOW_OFFSET_Y = 4
    SHADOW_PADDING = 8  # Extra space around the box for the painted shadow

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._voice_active = False
        self._voice_cancelled = False
        self._voice_error_message = None
        self._press_pos: Optional[QPoint] = None
        self._window_press_pos: Optional[QPoint] = None
        self._is_dragging = False
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

        # Expand button (shows floating pet when minimized)
        self.expand_button = QPushButton("▲", self)
        self.expand_button.setFixedSize(28, 28)
        self.expand_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_button.setToolTip("Show floating pet")
        self.expand_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(51, 65, 85, 0.85);
                color: #93c5fd;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 14px;
                font-size: 11px;
                font-weight: bold;
                padding-bottom: 1px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: #ffffff;
                border-color: #60a5fa;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
                color: #ffffff;
            }
        """)
        self.expand_button.clicked.connect(self.expand_clicked.emit)
        self.expand_button.hide()

        # Text input
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Hi!!")
        self.input_field.returnPressed.connect(self._handle_submit)
        
        font = QFont()
        font.setFamilies(["Segoe UI", "Nirmala UI", "Latha"])
        font.setPointSize(10)
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

        self.voice_bar = QWidget(self)
        bar_layout = QHBoxLayout(self.voice_bar)
        bar_layout.setContentsMargins(2, 0, 0, 0)
        bar_layout.setSpacing(8)
        self.voice_status = QLabel('Starting…', self.voice_bar)
        self.voice_status.setStyleSheet('color: #bfdbfe; font: 11px "Segoe UI"; border: none; background: transparent;')
        self.voice_status.setFixedWidth(92)
        self.waveform = AudioWaveform(self.voice_bar)
        bar_layout.addWidget(self.voice_status)
        bar_layout.addWidget(self.waveform, 1)
        self.voice_bar.hide()
        self.cancel_voice_button = QPushButton('×', self)
        self.cancel_voice_button.setFixedSize(28, 28)
        self.cancel_voice_button.setAccessibleName('Cancel speech recognition')
        self.cancel_voice_button.setToolTip('Cancel voice input')
        self.cancel_voice_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_voice_button.setStyleSheet('QPushButton { color: #cbd5e1; background: #334155; border: none; border-radius: 14px; font-size: 19px; } QPushButton:hover { background: #475569; color: white; }')
        self.cancel_voice_button.clicked.connect(self._cancel_voice_input)
        self.cancel_voice_button.hide()
        layout.addWidget(self.expand_button)
        layout.addWidget(self.voice_bar, 1)
        layout.addWidget(self.input_field, 1)
        layout.addWidget(self.voice_button)
        self.voice_button.setVisible(settings.VOICE_ENABLED)
        layout.addWidget(self.send_button)
        layout.addWidget(self.cancel_voice_button)

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
        painter.setPen(QPen(QColor(96, 165, 250, 160) if self._voice_active else QColor(255, 255, 255, 46), 1.0))
        painter.drawRoundedRect(box_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)

        painter.end()

    def set_expand_visible(self, visible: bool) -> None:
        """Sets visibility of the expand button."""
        self.expand_button.setVisible(visible)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Tracks the start of a mouse click/drag on the command box."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            win = self.window()
            if win:
                self._window_press_pos = win.pos()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Moves the parent window if dragged by the command box."""
        if self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            curr = event.globalPosition().toPoint()
            if not self._is_dragging and (curr - self._press_pos).manhattanLength() >= 6:
                self._is_dragging = True
            if self._is_dragging and self._window_press_pos is not None:
                diff = curr - self._press_pos
                win = self.window()
                if win:
                    win.move(self._window_press_pos + diff)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Emits drag_finished when dragging ends."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                win = self.window()
                self.drag_finished.emit(win.pos() if win else QPoint())
            self._is_dragging = False
            self._press_pos = None
            self._window_press_pos = None
        super().mouseReleaseEvent(event)

    def _handle_submit(self) -> None:
        """Processes and emits the command."""
        if self._voice_active:
            return
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
        if not settings.VOICE_ENABLED or not SPEECH_AVAILABLE or self._voice_active:
            return
        if self._voice_worker and self._voice_worker.isRunning():
            return
        self._voice_cancelled = False
        self._voice_error_message = None
        self._set_voice_mode(True)
        self.voice_status.setText('Starting…')
        self._voice_worker = VoiceInputWorker(parent=self)
        self._voice_worker.listening_started.connect(self._on_voice_listening)
        self._voice_worker.audio_level_changed.connect(self.waveform.set_level)
        self._voice_worker.partial_recognized.connect(self._on_voice_partial)
        self._voice_worker.processing_started.connect(self._on_voice_processing)
        self._voice_worker.speech_recognized.connect(self._on_voice_recognized)
        self._voice_worker.error_occurred.connect(self._on_voice_error)
        # Restore idle only when QThread has truly finished, so retry cannot race it.
        self._voice_worker.finished.connect(self._on_voice_stopped)
        self._voice_worker.start()

    def _set_voice_mode(self, active):
        self._voice_active = active
        self.input_field.setVisible(not active)
        self.send_button.setVisible(not active)
        self.voice_button.setVisible(not active and settings.VOICE_ENABLED)
        self.voice_bar.setVisible(active)
        self.cancel_voice_button.setVisible(active)
        if not active:
            self.waveform.stop()
        self.update()

    def _on_voice_listening(self):
        if self._voice_cancelled:
            return
        self.voice_status.setText('Listening…')
        self.waveform.start()
        self.voice_started.emit()

    def _on_voice_partial(self, text):
        if self._voice_cancelled:
            return
        self.voice_status.setText(self.voice_status.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 92))
        self.voice_status.setToolTip(text)
        self.voice_bar.setAccessibleDescription(text)

    def _on_voice_processing(self):
        if self._voice_cancelled:
            return
        self.voice_status.setText('Recognizing…')
        self.waveform.stop()

    def _cancel_voice_input(self):
        self._voice_cancelled = True
        self.voice_status.setText('Cancelling…')
        self.cancel_voice_button.setEnabled(False)
        if self._voice_worker:
            self._voice_worker.cancel()

    def _on_voice_recognized(self, text):
        if self._voice_cancelled:
            return
        self.input_field.setText(text)
        # Dedicated signal keeps spoken alias matching out of typed command paths.
        self.voice_command_submitted.emit(text)

    def _on_voice_error(self, error_msg):
        if self._voice_cancelled:
            return
        self._voice_error_message = error_msg
        self.voice_error.emit(error_msg)

    def _on_voice_stopped(self):
        self._set_voice_mode(False)
        self.cancel_voice_button.setEnabled(True)
        self.voice_button.set_idle()
        if self._voice_error_message:
            self.input_field.setPlaceholderText(self._voice_error_message)
        else:
            self._restore_placeholder()
        worker = self._voice_worker
        self._voice_worker = None
        if worker:
            worker.deleteLater()
        self.input_field.setFocus()

    def _restore_placeholder(self):
        self.input_field.setPlaceholderText('Hi!!')
