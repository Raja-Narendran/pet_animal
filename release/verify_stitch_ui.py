"""Render the Manager with isolated fixture data; never launch user applications."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--scale', default='1')
parser.add_argument('--output', default='build/stitch-ui')
args = parser.parse_args()
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_SCALE_FACTOR'] = args.scale
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication
from src.app.controller import ApplicationController
from src.app.manager_window import PAGES
from src.app.manager_ui.theme import load_font
from src.config.settings import settings
from src.core.application import ApplicationCore

class VerificationLauncher:
    def open_application(self, key): return True, 'Opened sample application'
    def open_registered_url(self, url): return True, 'Opened sample website'
    def open_local_result(self, path, **kwargs): return True, 'Opened sample file'

output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
report = dict(scale=args.scale, font=load_font(), captures=[], problems=[])
with tempfile.TemporaryDirectory(prefix='pet-stitch-ui-') as temp:
    settings.STATE_FILE = Path(temp)/'state.json'
    core = ApplicationCore(Path(temp)/'data', VerificationLauncher())
    core.confirm_name('Alex')
    categories = core.categories()
    personal = next(c['id'] for c in categories if c['name'] == 'Personal Information')
    sensitive = next(c['id'] for c in categories if 'password' in c['name'].lower())
    core.memory_service.create_memory(personal, 'Email ID', 'user.email', 'alex@example.test')
    private = core.memory_service.create_memory(sensitive, 'GitHub Token', 'github.token', 'fixture-only-secret')
    routine = core.workflows.save('Morning Dev Setup', ['start work', 'begin day'], [
        dict(type='application', value='vscode'), dict(type='url', value='https://example.com'),
        dict(type='wait', value=2.5), dict(type='message', value='Ready for your day!')])
    core.execute('open notepad')
    controller = ApplicationController(core)
    try:
        for theme in ('light', 'dark'):
            core.save_settings(dict(core.app_settings(), theme=theme))
            for width,height in ((1200,900),(1600,1000),(850,650)):
                controller.manager.resize(width,height)
                for page in PAGES:
                    controller.show_manager(page)
                    if page == 'Workflows': controller.manager.workflows_panel.open_routine(routine)
                    if page == 'Memory':
                        m = controller.manager
                        m.memory_table.selectRow(next(i for i,r in enumerate(m.memory_records) if r['id'] == private))
                        assert m.memory_detail_value.toPlainText() == '••••••••'
                    app.processEvents()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    app.processEvents()
                    m = controller.manager
                    name = f"{theme}-{width}x{height}-{page.lower().replace(' ', '-')}.png"
                    file = output/name
                    assert m.grab().save(str(file))
                    actual = [m.width(),m.height()]
                    horizontal = m.content_scroll.horizontalScrollBar().maximum()
                    report['captures'].append(dict(page=page, theme=theme, requested=[width,height], actual=actual, horizontal_overflow=horizontal, image=str(file)))
                    if actual != [width,height] or horizontal:
                        report['problems'].append(dict(page=page, theme=theme, size=[width,height], actual=actual, horizontal=horizontal))
        assert core.db.execute('PRAGMA user_version').fetchone()[0] == 7
    finally:
        core.listeners.clear()
        app.aboutToQuit.disconnect(controller.shutdown)
        controller.shutdown()
        controller.manager.hide()
        controller.pet.hide()
report['success'] = not report['problems'] and report['font'] == 'Inter'
(output/'verification.json').write_text(json.dumps(report,indent=2), encoding='utf-8')
print(json.dumps(dict(success=report['success'],captures=len(report['captures']),problems=report['problems'],font=report['font'])))
raise SystemExit(0 if report['success'] else 1)
