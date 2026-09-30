# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[('petimage', 'petimage'), ('src/database/migrations', 'src/database/migrations'), ('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['release/runtime_diagnostics.py'],
    excludes=['selenium', 'speech_recognition', 'sounddevice', 'numpy', 'pytest'],
    noarchive=False,
    optimize=0,
)
# This Qt build uses the Windows ICU ABI. A PATH ICU build has incompatible
# version-suffixed exports and must not shadow the OS library.
from pathlib import Path
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
