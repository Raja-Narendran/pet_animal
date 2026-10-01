# Release verification

Validation date: 30 September 2026, Windows 11, Python 3.14.3.

## Automated suite

The complete suite passed: **175 tests**. This includes the original 141 tests and 34 V2 cases covering SQLite migration/restart, memory CRUD, invalid/duplicate records, parameterized input, import rollback, Windows DPAPI, normalized phrases, reserved-pattern protection, rejected actions/URL schemes, missing applications, redacted unsupported inputs, history/statistics, backup integrity/schema rejection and recovery, asset validation/path containment, profile switching, independent windows, confirmation/cancellation, and installer archive containment.

One existing development dependency warning remains: SpeechRecognition imports the deprecated `aifc` compatibility package. V2 disables voice and excludes SpeechRecognition and sounddevice from the Windows release.

## Visual verification

All six Manager pages were rendered with an isolated temporary database. Windows Segoe UI fonts were loaded explicitly for Qt's offscreen renderer. Light/dark dashboard previews, Pet Studio, and the floating pet were inspected. Fixed issues included primary-button contrast and compressed panel/button heights. Actions now retain a 40-pixel minimum height and panels scroll when their content exceeds the viewport.

Previews are stored under `docs/screenshots`. Dashboard numbers in these previews are the actual empty verification database's counts; they are not fabricated production metrics.

## Packaging

The executable and installer are built by `release/build.ps1` with the existing PyInstaller environment. Migration SQL, original pet sprite sheets and Figma icons are bundled. Optional voice/browser automation dependencies are excluded.

A real frozen startup test found a DLL ABI conflict: PyInstaller collected a PATH-provided `icuuc.dll` whose versioned exports differed from the Windows ICU ABI used by this Qt build. The spec excludes that DLL and its data file, allowing Qt to use Windows' system ICU as it does in development. A diagnostic build passed its complete self-test after this fix. The self-test runtime hook captures exceptions in a report/log instead of leaving a hidden error dialog.

**Final result: both the packaged executable and the installer payload passed.** Reports are saved as `docs/packaged-verification.json` and `docs/installer-verification.json`.

The final packaged executable and setup payload are verified with:

```powershell
Start-Process -Wait -WindowStyle Hidden -FilePath .\dist\v2\pet-animal\pet-animal.exe -ArgumentList '--self-test', 'K:\pet_animal\build\packaged-verification.json'
Start-Process -Wait -WindowStyle Hidden -FilePath .\dist\v2\Pet-Animal-2.0-Setup.exe -ArgumentList '--verify-payload', 'K:\pet_animal\build\installer-verification.json'
```

The setup check validates the embedded ZIP's CRCs, extracts into a temporary folder, then runs that extracted executable's full self-test. Neither check installs the application, registers uninstall, creates a Start menu shortcut or launches external applications.

## Verification boundaries

Interactive installation/uninstallation, Windows 10 execution, physical multi-monitor dragging, system tray interactions and launching real Chrome/VS Code were not exercised. Native application launches are mocked in the automated suite; startup/window checks use Qt's offscreen renderer. The install/uninstall implementation is reviewable in `release/installer.py`, and the installer can be run by the user to perform installation. Artifacts are unsigned.

Database backups preserve the SQLite data, not imported pet image files. Restore rejects backups whose assets are missing and encrypted values require the same Windows user. Configuration JSON imports are additive and reject conflicting command phrases. The startup option applies when the application starts; Windows login autorun is not configured.

Pre-existing edits to `src/services/youtube_automation.py` and `tests/test_youtube_automation.py` were preserved. `git diff --check` reports one pre-existing trailing-whitespace line in that YouTube file; it was left untouched.

## Final installer artifact

`dist/v2/Pet-Animal-2.0-Setup.exe` — 59,602,658 bytes.

SHA-256: `1DEACB0A25F39A8DB1D640DDAB06D7D05BD954F1BB64D86D83D064E43CDFDD61`.
