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
            from src.services.software_discovery import DiscoveredApplication, DiscoverySource, SoftwareDiscoveryService
            executable = Path(temp) / 'DiscoveryVerification.exe'
            executable.write_bytes(b'MZ')
            candidate = DiscoveredApplication.candidate('Discovery Verification', str(executable), DiscoverySource.START_MENU_USER)
            assert not core.interpret('open discovery verification').matched
            summary = core.register_discovered_applications([candidate])
            assert summary['added'] == 1 and summary['commands_created'] == 1
            application_id = core.list_registered_applications()[0].id
            assert core.register_discovered_applications([candidate])['added'] == 0
            assert core.interpret('discovery verification open pannu').intent.target == application_id
            core.set_application_enabled(application_id, False)
            assert core.execute('open discovery verification')['message'] == 'Discovery Verification is currently disabled.'
            core.set_application_enabled(application_id, True)
            discovery_backup = core.backup()
            executable.unlink()
            core.restore(discovery_backup)
            assert core.get_registered_application(application_id).needs_repair
            core.unregister_application(application_id)
            assert not core.interpret('can you open discovery verification').matched
            # Keep the existing parse-only history assertion below meaningful.
            core.clear_history()
            service = SoftwareDiscoveryService()
            detected = service.discover()
            assert not service.errors, 'A Windows discovery provider failed.'
            result['software_discovery'] = dict(candidates=len(detected), launchable=sum(item.launchable for item in detected))
            core.confirm_name('Verification user')
            assert core.execute('what is my name')['message'] == 'Verification user'
            assert core.db.execute('PRAGMA user_version').fetchone()[0] == 3
            service = core.memory_service
            category = next(c['id'] for c in core.categories() if c['name'] == 'Custom')
            editor = core.execute('remember my editor is VS Code')
            core.confirm_memory(editor['memory_confirmation'])
            preference = service.get_by_key('preferred.editor', consume=False)
            assert core.interpret('open my editor').intent.target == 'vscode'
            assert core.get_memory(preference['id'])['access_count'] == 0
            project = service.create_memory(category, 'Pet Animal project', 'project.pet_animal.path', 'K:\\pet_animal',
                tags=['development'], aliases=['project location'])
            service.create_relationship(preference['id'], 'used_for', project)
            assert core.execute('what is my pet animal project path')['message'] == 'K:\\pet_animal'
            assert core.memory_retriever.get_by_key('project location').memory_id == project
            assert service.get_relationships(project)
            private_category = next(c['id'] for c in core.categories() if c['sensitive'])
            private = service.create_memory(private_category, 'Private verification', 'private.verification', 'DPAPI verification value')
            assert core.get_memory(private)['memory_value'] == '••••••••'
            exported = core.export_memories()
            assert exported['version'] == 2
            assert all(record['memory_key'] != 'private.verification' for record in exported['memories'])
            assert core.habit_engine.analyze() == []
            session_memory = service.create_memory(category, 'Session verification', 'current_task', 'Verify memory', memory_type='CONTEXT')
            backup = core.backup()
            core.confirm_name('Changed')
            core.restore(backup)
            assert core.execute('what is my name')['message'] == 'Verification user'
            assert core.get_memory(session_memory) is None
            assert service.get_relationships(project)
            assert core.get_memory(private, reveal=True)['memory_value'] == 'DPAPI verification value'
            result['personal_memory_engine'] = dict(schema_version=3, preference_resolution=True,
                aliases_tags_relationships=True, access_tracking=True, dpapi_safe_export=True,
                session_restore_cleanup=True, habit_analysis_on_demand=True)
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
            from src.commands.interpreter import IntentType, MatchReason
            smart = core.interpret('Can you open Chrome please?')
            assert smart.matched and smart.command_id and smart.intent.intent == IntentType.OPEN_APPLICATION
            assert core.interpret('chrome open panna vendam').reason == MatchReason.NEGATED_COMMAND
            controller.manager.navigation.setCurrentRow(2)
            controller.manager.smart_input.setText('Chrome ah open pannu')
            controller.manager.smart_test_button.click()
            assert 'Execution: Not executed' in controller.manager.smart_result.text()
            assert not core.history()
            controller.quit()
            assert not controller.pet.tray_icon.isVisible()
            result.update(success=True, checks=['SQLite migration', 'memory persistence', 'backup restore', 'six Manager pages', 'live profile switching', 'independent Manager closing', 'offline English and Tamil engines, models, native decoder, and voice command routing', 'smart command resolution, negation and parse-only Manager tester', 'software discovery, user-authorized bulk refresh registration, duplicate refresh, dynamic Tanglish aliases, disable, missing-path restore and removal', 'quit cleanup'])
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
