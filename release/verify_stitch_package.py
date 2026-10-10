"""Verify bundled Manager resources; pair with the frozen executable self-test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from types import CodeType
from PyInstaller.archive.readers import CArchiveReader

parser = argparse.ArgumentParser()
parser.add_argument('--root', default='dist/v2/pet-animal')
parser.add_argument('--output', default='build/stitch-packaged-assets.json')
args = parser.parse_args()
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from src.config.settings import settings
from src.app.manager_ui.icons import icon
from src.app.manager_ui.theme import load_font

bundle = Path(args.root).resolve() / '_internal'
app = QApplication([])
settings.BASE_DIR = bundle
manifest = json.loads((bundle / 'assets/ui/stitch/sources.json').read_text(encoding='utf-8'))
report = dict(bundle=str(bundle), resources=[], icons=[], modules=[], font=load_font(), problems=[])
for entry in manifest:
    path = bundle / entry['path']
    valid = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
    report['resources'].append(dict(path=entry['path'], hash_matches=valid))
    if not valid:
        report['problems'].append('Missing or changed bundled resource: ' + entry['path'])
for path in sorted((bundle / 'assets/ui/stitch').glob('*.svg')):
    for scale in (1, 1.25, 1.5):
        valid = not icon(path.stem, '#115086', 24, scale).isNull()
        report['icons'].append(dict(name=path.stem, scale=scale, loads=valid))
        if not valid:
            report['problems'].append('Cannot load bundled SVG: ' + path.name)
if report['font'] != 'Inter':
    report['problems'].append('Bundled Inter did not load')
# Confirm the executable contains the final presentation source, rather than stale bytecode.
executable = CArchiveReader(str(Path(args.root).resolve() / 'pet-animal.exe'))
archive = executable.open_embedded_archive(next(name for name, entry in executable.toc.items() if entry[-1] == 'z'))
def normalize(code):
    return code.replace(co_filename='', co_consts=tuple(
        normalize(value) if isinstance(value, CodeType) else value for value in code.co_consts))
project = Path(__file__).resolve().parents[1]
modules = [project / 'src/app' / name for name in ('manager_window.py', 'workflow_panel.py', 'software_discovery.py')]
modules.extend(sorted((project / 'src/app/manager_ui').glob('*.py')))
for path in modules:
    name = '.'.join(path.relative_to(project).with_suffix('').parts)
    if path.name == '__init__.py':
        name = name.rsplit('.', 1)[0]
    source = compile(path.read_text(encoding='utf-8'), str(path), 'exec', dont_inherit=True, optimize=0)
    valid = normalize(archive.extract(name)) == normalize(source)
    report['modules'].append(dict(name=name, matches_source=valid))
    if not valid:
        report['problems'].append('Packaged UI bytecode differs from source: ' + name)
report['success'] = not report['problems'] and len(report['icons']) == 90
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(dict(success=report['success'], font=report['font'], resources=len(report['resources']), icon_checks=len(report['icons']), module_checks=len(report['modules']), problems=report['problems'])))
raise SystemExit(0 if report['success'] else 1)
