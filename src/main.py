"""Main application entry point for Pet Animal Desktop Companion."""
import sys
import ctypes
from pathlib import Path

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from src.config.settings import settings
from src.utils.logger import setup_logger
from src.app.pet_window import PetWindow


def enable_windows_dpi_awareness():
    """Enables Windows Per-Monitor High-DPI awareness for crisp rendering."""
    if sys.platform == "win32":
        try:
            # PROCESS_PER_MONITOR_DPI_AWARE = 2
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def main():
    """Starts the Pet Animal desktop companion application."""
    enable_windows_dpi_awareness()

    logger = setup_logger("main")
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION}...")

    # Enable High DPI pixmaps
    app = QApplication(sys.argv)
    app.setApplicationName(settings.APP_NAME)
    app.setOrganizationName("PetAnimal")

    # Don't quit if window is hidden to tray
    app.setQuitOnLastWindowClosed(False)

    # Create and display desktop companion
    window = PetWindow()
    window.show()

    logger.info("Pet Animal running. Entering event loop.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
