"""A non-draggable local sprite preview with an owned animation timer."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel
from ...config.settings import settings

class SpritePreview(QLabel):
    def __init__(self):
        super().__init__()
        self.frames = []
        self.index = 0
        self.animated = False
        self.path = None
        self.size = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(220, 220)
        self.timer = QTimer(self)
        self.timer.setInterval(settings.ANIMATION_INTERVAL_MS)
        self.timer.timeout.connect(self.advance)
    def configure(self, path, size, animated):
        self.animated = bool(animated)
        size = min(200, size)
        if (str(path), size) != (self.path, self.size):
            self.path, self.size = str(path), size
            sheet = QPixmap(self.path)
            self.frames = [sheet.copy(i * sheet.height(), 0, sheet.height(), sheet.height()).scaled(
                size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
                for i in range(sheet.width() // sheet.height())] if not sheet.isNull() else []
            self.index = 0
            self.paint_frame()
        if animated and len(self.frames) > 1 and self.isVisible(): self.timer.start()
        else: self.timer.stop()
    def paint_frame(self):
        if self.frames: self.setPixmap(self.frames[self.index])
        else: self.setText('Preview unavailable')
    def advance(self):
        if self.frames:
            self.index = (self.index + 1) % len(self.frames)
            self.paint_frame()
    def stop(self): self.timer.stop()
    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)
    def showEvent(self, event):
        super().showEvent(event)
        if self.animated and len(self.frames) > 1:
            self.timer.start()
