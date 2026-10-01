"""Audio-reactive waveform; all amplitudes originate from microphone PCM."""
from collections import deque
from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget


class AudioWaveform(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(50)
        self.setFixedHeight(28)
        self.setAccessibleName('Microphone audio waveform')
        self.levels = deque([0.0] * 32, maxlen=32)
        self.target_level = 0.0
        self.display_level = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._advance)

    def set_level(self, level):
        self.target_level = max(0.0, min(1.0, float(level)))

    def start(self):
        self.reset()
        self.timer.start()

    def stop(self):
        self.timer.stop()
        self.reset()

    def reset(self):
        self.levels = deque([0.0] * 32, maxlen=32)
        self.target_level = self.display_level = 0.0
        self.update()

    def _advance(self):
        smoothing = 0.6 if self.target_level > self.display_level else 0.25
        self.display_level += (self.target_level - self.display_level) * smoothing
        self.levels.append(self.display_level)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        spacing = self.width() / len(self.levels)
        width = max(1.5, min(3.5, spacing - 2))
        for index, level in enumerate(self.levels):
            height = 3 + level * (self.height() - 5)
            color = QColor('#60a5fa' if level < 0.72 else '#a5b4fc')
            color.setAlphaF(0.4 + 0.6 * level)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(index * spacing, (self.height() - height) / 2, width, height), width / 2, width / 2)
