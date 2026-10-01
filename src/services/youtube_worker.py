"""Background worker thread for running YouTube automation without freezing the GUI."""
from PyQt6.QtCore import QThread, pyqtSignal
from .youtube_automation import YouTubeAutomationService
from ..utils.logger import get_logger

logger = get_logger("youtube_worker")


class YouTubePlayWorker(QThread):
    """Executes YouTube automation in a background thread."""

    playback_started = pyqtSignal(str)
    playback_failed = pyqtSignal(str)

    def __init__(self, song_name: str, parent=None):
        super().__init__(parent)
        self.song_name = song_name

    def run(self) -> None:
        """Runs the YouTube playback automation."""
        logger.info('Starting background YouTube playback.')
        try:
            success, message = YouTubeAutomationService.play_song(self.song_name)
            if success:
                self.playback_started.emit(message)
            else:
                self.playback_failed.emit(message)
        except Exception as e:
            logger.exception(f"Unexpected error in YouTube worker: {e}")
            self.playback_failed.emit(f"Could not play song: {e}")
