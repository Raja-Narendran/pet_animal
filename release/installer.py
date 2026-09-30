"""User-level Windows installer, built separately with an embedded app archive."""
import os
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def unpack(archive, target):
    target = Path(target).resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            destination = (target / member.filename).resolve()
            if not destination.is_relative_to(target):
                raise ValueError('Unsafe installation archive.')
        package.extractall(target)


def install(archive, local_appdata, appdata):
    import winreg
    base = Path(local_appdata).resolve() / 'Programs'
    base.mkdir(parents=True, exist_ok=True)
    target = base / 'Pet Animal'
    if target.exists():
        raise ValueError('Pet Animal is already installed. Uninstall it in Windows Settings before installing this version. Your local data will be preserved.')
    staging = Path(tempfile.mkdtemp(prefix='PetAnimal-setup-', dir=base))
    try:
        unpack(archive, staging)
        if not (staging / 'pet-animal.exe').is_file():
            raise ValueError('The installer archive is incomplete.')
        staging.rename(target)
    finally:
        if staging.exists() and staging.parent == base:
            shutil.rmtree(staging)
    # Install a fixed-scope uninstall script; it never removes the data directory.
    uninstall = target / 'uninstall.ps1'
    uninstall.write_text('''$ErrorActionPreference = 'Stop'
$installTarget = Join-Path $env:LOCALAPPDATA 'Programs\\Pet Animal'
$resolvedTarget = [IO.Path]::GetFullPath($installTarget)
$expectedTarget = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\\Pet Animal'))
if ($resolvedTarget -ne $expectedTarget -or $PSScriptRoot -ne $resolvedTarget) { throw 'Invalid uninstall location' }
$running = Get-Process -Name 'pet-animal' -ErrorAction SilentlyContinue
if ($running) { throw 'Quit Pet Animal from its system tray before uninstalling.' }
$link = Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs\\Pet Animal.lnk'
if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link }
Remove-Item -LiteralPath 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\PetAnimal' -ErrorAction SilentlyContinue
Set-Location -LiteralPath $env:TEMP
Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
''', encoding='utf-8-sig')
    link = Path(appdata) / 'Microsoft/Windows/Start Menu/Programs/Pet Animal.lnk'
    link.parent.mkdir(parents=True, exist_ok=True)
    # Paths are supplied as environment data, never interpolated into shell source.
    script = "$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($env:PET_INSTALL_LINK); $shortcut.TargetPath=$env:PET_INSTALL_EXE; $shortcut.WorkingDirectory=$env:PET_INSTALL_DIR; $shortcut.Save()"
    environment = dict(os.environ, PET_INSTALL_LINK=str(link), PET_INSTALL_EXE=str(target / 'pet-animal.exe'), PET_INSTALL_DIR=str(target))
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script], env=environment, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Uninstall\PetAnimal') as key:
        for name, value in {'DisplayName':'Pet Animal', 'DisplayVersion':'2.0.0', 'Publisher':'Pet Animal', 'InstallLocation':str(target), 'UninstallString':f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{uninstall}"'}.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, 'NoModify', 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, 'NoRepair', 0, winreg.REG_DWORD, 1)
    return target


def main():
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.title('Pet Animal 2.0 Setup')
    root.geometry('520x250')
    root.resizable(False, False)
    tk.Label(root, text='Pet Animal', font=('Segoe UI', 24, 'bold'), fg='#3368A0').pack(pady=(24, 8))
    tk.Label(root, text='Install your local desktop companion for this Windows user.\nIncludes the Manager and floating husky. No administrator access needed.', font=('Segoe UI', 10)).pack(pady=8)
    status = tk.Label(root, text='Your memories are kept separately in LocalAppData.', font=('Segoe UI', 9))
    status.pack(pady=8)
    def run():
        install_button.config(state='disabled')
        status.config(text='Installing…')
        root.update()
        try:
            resource = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'pet-animal-app.zip'
            target = install(resource, os.environ['LOCALAPPDATA'], os.environ['APPDATA'])
            messagebox.showinfo('Installation complete', 'Open Pet Animal from the Windows Start menu.\nInstalled at: ' + str(target), parent=root)
            root.destroy()
        except Exception as error:
            messagebox.showerror('Installation failed', str(error), parent=root)
            status.config(text='Installation did not complete.')
            install_button.config(state='normal')
    install_button = tk.Button(root, text='Install Pet Animal', command=run, bg='#3368A0', fg='white', padx=24, pady=8, font=('Segoe UI', 10, 'bold'))
    install_button.pack(pady=8)
    root.mainloop()


if __name__ == '__main__':
    if '--verify-payload' in sys.argv:
        report_path = Path(sys.argv[sys.argv.index('--verify-payload') + 1])
        resource = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'pet-animal-app.zip'
        with zipfile.ZipFile(resource) as archive:
            assert archive.testzip() is None
        with tempfile.TemporaryDirectory(prefix='pet-animal-setup-check-') as temporary:
            unpack(resource, temporary)
            executable = Path(temporary) / 'pet-animal.exe'
            result_path = Path(temporary) / 'result.json'
            subprocess.run([str(executable), '--self-test', str(result_path)], check=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            result = json.loads(result_path.read_text(encoding='utf8'))
            assert result['success']
            result['installer_archive_verified'] = True
            report_path.write_text(json.dumps(result, indent=2), encoding='utf8')
    else:
        main()
