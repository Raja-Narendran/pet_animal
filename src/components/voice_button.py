"""Microphone toggle button for voice input."""
from typing import Optional
from PyQt6.QtWidgets import QPushButton, QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from ..utils.logger import get_logger

logger = get_logger("voice_button")


class VoiceButton(QPushButton):
    """Circular microphone button with listening/idle state styling.

    Signals:
        voice_toggled(): Emitted when the button is clicked to start listening.
    """

    voice_toggled = pyqtSignal()

    # Visual states
    STYLE_IDLE = """
        QPushButton {
            background-color: rgba(30, 41, 59, 0.85);
            color: #94a3b8;
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 16px;
            font-size: 14px;
            padding-bottom: 1px;
        }
        QPushButton:hover {
            background-color: rgba(51, 65, 85, 0.95);
            color: #ffffff;
            border-color: rgba(255, 255, 255, 0.3);
        }
        QPushButton:pressed {
            background-color: rgba(71, 85, 105, 0.95);
        }
    """

    STYLE_LISTENING = """
        QPushButton {
            background-color: #ef4444;
            color: #ffffff;
            border: 1px solid #ef4444;
            border-radius: 16px;
            font-size: 14px;
            padding-bottom: 1px;
        }
        QPushButton:hover {
            background-color: #dc2626;
        }
    """

    STYLE_DISABLED = """
        QPushButton {
            background-color: rgba(30, 41, 59, 0.4);
            color: #475569;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            font-size: 14px;
            padding-bottom: 1px;
        }
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("🎤", parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Voice input (click to speak)")
        self._is_listening = False
        self.set_idle()
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self) -> None:
        """Only emit toggle when not already listening."""
        if not self._is_listening:
            self.voice_toggled.emit()

    def set_listening(self) -> None:
        """Switch to 'recording' visual state."""
        self._is_listening = True
        self.setStyleSheet(self.STYLE_LISTENING)
        self.setToolTip("Listening... speak your command")
        self.setText("⏺")

    def set_idle(self) -> None:
        """Switch to normal idle visual state."""
        self._is_listening = False
        self.setStyleSheet(self.STYLE_IDLE)
        self.setToolTip("Voice input (click to speak)")
        self.setText("🎤")

    def set_unavailable(self) -> None:
        """Disable button when voice input is not available."""
        self._is_listening = False
        self.setEnabled(False)
        self.setStyleSheet(self.STYLE_DISABLED)
        self.setToolTip("Local voice unavailable (check Vosk model and microphone dependencies)")
        self.setCursor(Qt.CursorShape.ForbiddenCursor)
