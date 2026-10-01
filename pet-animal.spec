# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs


a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=collect_dynamic_libs('vosk'),
    datas=[('petimage', 'petimage'), ('assets/ui', 'assets/ui'),
           ('assets/speech', 'assets/speech'),
           ('src/database/migrations', 'src/database/migrations')],
    hiddenimports=[],
    hookspath=['release/hooks'],
    hooksconfig={},
    runtime_hooks=['release/runtime_diagnostics.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Some PATH installations expose an ICU build incompatible with Qt's exports.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pet-animal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pet-animal',
)
