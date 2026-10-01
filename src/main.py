"""Main application entry point for Pet Animal Desktop Companion."""
import sys
import ctypes
import os
import json
import tempfile
from pathlib import Path

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from src.config.settings import settings
from src.utils.logger import setup_logger
from src.app.controller import ApplicationController
from src.core.application import ApplicationCore
from src.config.settings import _get_data_dir


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

    self_test = '--self-test' in sys.argv
    if self_test:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    # Enable High DPI pixmaps
    app = QApplication(sys.argv)
    app.setApplicationName(settings.APP_NAME)
    app.setOrganizationName("PetAnimal")

    # Don't quit if window is hidden to tray
    app.setQuitOnLastWindowClosed(False)

    if self_test:
        run_self_test(app)
        return

    # Create and display desktop companion
    core = ApplicationCore(_get_data_dir())
    controller = ApplicationController(core)

    logger.info("Pet Animal running. Entering event loop.")
    sys.exit(app.exec())


def run_self_test(app):
    """Validate the frozen executable with isolated data and no external launches."""
    from PyQt6.QtGui import QFontDatabase
    from src.core.application import DEFAULT_PET
    for filename in ('segoeui.ttf', 'segoeuib.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / filename))
    report_path = Path(sys.argv[sys.argv.index('--self-test') + 1])
    result = dict(success=False, version=settings.VERSION)
    with tempfile.TemporaryDirectory(prefix='pet-animal-verification-') as temp:
        settings.STATE_FILE = Path(temp) / 'state.json'
        core = ApplicationCore(temp)
        controller = ApplicationController(core)
        try:
            core.confirm_name('Verification user')
            assert core.execute('what is my name')['message'] == 'Verification user'
            backup = core.backup()
            core.confirm_name('Changed')
            core.restore(backup)
            assert core.execute('what is my name')['message'] == 'Verification user'
            for index in range(6):
                controller.manager.navigation.setCurrentRow(index)
                app.processEvents()
            core.save_profile('Verification pet', 'builtin-idle', dict(DEFAULT_PET, size=128))
            assert controller.pet.pet.width() == 128
            controller.show_pet()
            controller.manager.close()
            app.processEvents()
            assert controller.pet.isVisible() and not controller.manager.isVisible()
            assert not controller.pet.command_box.voice_button.isHidden()
            from src.services.voice_input import SPEECH_AVAILABLE
            assert SPEECH_AVAILABLE, 'Local speech engine or audio capture dependency is unavailable.'
            from src.services.voice_input import create_recognizer
            recognizer = create_recognizer()
            recognizer.AcceptWaveform(bytes(32000))
            assert 'text' in json.loads(recognizer.FinalResult())
            from src.services.voice_input import get_multilingual_model, SpeechEndpoint, transcribe_multilingual
            assert get_multilingual_model().model.is_multilingual
            assert isinstance(transcribe_multilingual(bytes(32000), 16000), str)
            assert not SpeechEndpoint().feed(bytes(640), 16000)
            assert core.resolve_voice_phrase('Shape of You பாட்டு play பண்ணு') == 'play shape of you'
            assert core.resolve_voice_phrase('Chrome open பண்ணு') == 'open chrome'
            controller.quit()
            assert not controller.pet.tray_icon.isVisible()
            result.update(success=True, checks=['SQLite migration', 'memory persistence', 'backup restore', 'six Manager pages', 'live profile switching', 'independent Manager closing', 'offline English and Tamil engines, models, native decoder, and voice command routing', 'quit cleanup'])
        except Exception as error:
            result['error'] = str(error)
        finally:
            app.aboutToQuit.disconnect(controller.shutdown)
            controller.shutdown()
            controller.manager.hide()
            controller.pet.hide()
    report_path.write_text(json.dumps(result, indent=2), encoding='utf8')
    if not result['success']:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
