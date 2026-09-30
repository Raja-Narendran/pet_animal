param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not $SkipTests) {
    & .venv\Scripts\python.exe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
}
& .venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist/v2 --workpath build/v2 pet-animal.spec
if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
& .venv\Scripts\python.exe -c "from pathlib import Path; import zipfile; root=Path('dist/v2/pet-animal'); archive=zipfile.ZipFile('build/pet-animal-app.zip','w',zipfile.ZIP_DEFLATED); [archive.write(p,p.relative_to(root)) for p in root.rglob('*') if p.is_file()]; archive.close()"
if ($LASTEXITCODE -ne 0) { throw 'Archive creation failed.' }
$petArchivePath = Join-Path (Get-Location).Path 'build\pet-animal-app.zip'
& .venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name Pet-Animal-2.0-Setup --distpath dist/v2 --workpath build/installer --specpath build --add-data "$petArchivePath;." release/installer.py
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
