# Software Discovery verification

Historical report for the initial per-application approval release. The user subsequently authorized automatic registration on Refresh; see `software-discovery-auto-add-verification.md` for the current behavior and release results.

Verified on Windows 11, Python 3.14.3, on 2026-10-01 (Asia/Calcutta).

## Architecture

Manual refresh → structured Windows providers → executable validation → deduplication/metadata merge → Manager review → explicit approval → SQLite registration and optional command → existing Smart Command resolution → WindowsLauncher.

Detection records are immutable and ephemeral. A scan never calls registration, modifies the command registry, or launches a process. A QThread scans without accessing the core's SQLite connection; Qt signals return results to the Manager. Scans are cancellable between records/providers, survive page navigation, and stop during application shutdown. No automatic startup scan or persistent installed-software cache is added.

The six-page Manager remains intact. The Commands page contains Applications and Discover Software tabs below the existing commands and parse-only tester. Search uses names/publishers; filters cover All, Launchable, Already Added, Needs Review, and Invalid. The approval dialog shows the executable and publisher and allows aliases, optional command creation, and phrase editing before saving. Registration and command creation share one transaction, so phrase conflicts roll back approval. Approved applications can be renamed, enabled/disabled, edited, or removed. Removal leaves installed software untouched and disables associated commands.

## Files added

- `src/services/software_discovery/__init__.py`
- `src/services/software_discovery/models.py` — immutable candidate/registration models and source/status enums.
- `src/services/software_discovery/validator.py` — shared discovery, approval, restore, and launch validation.
- `src/services/software_discovery/start_menu.py` — native read-only Shell link handling.
- `src/services/software_discovery/registry.py` — Windows Uninstall metadata providers.
- `src/services/software_discovery/service.py` — service, deduplicator, and known-name PATH provider.
- `src/app/software_discovery.py` — background worker, scan state, and Manager review controls.
- `src/database/migrations/002_registered_applications.sql`
- `tests/test_software_discovery.py`
- `tests/test_application_registration.py`
- `tests/test_software_discovery_ui.py`
- This report, the source/packaged/installer verification JSON reports, artifact hash JSON, and `docs/screenshots/software-discovery.png`.

## Files modified for this task

- `src/core/application.py` — migration, trusted-registration CRUD, aliases, dynamic action authorization, execution checks, configuration imports/exports, and compatible backup restore.
- `src/services/windows_launcher.py` — lookup by trusted ID and final path/status revalidation.
- `src/app/manager_window.py` — discovery section and approved-application command choices.
- `src/app/controller.py` — discovery-worker shutdown.
- `src/main.py` — frozen/source self-test coverage for discovery and registration lifecycle.
- `tests/test_application_core.py` — expected schema version changes from 1 to 2.
- `README.md` — user workflow and security/restore behavior.

The checkout already contained uncommitted Smart Command and other feature changes. Those were preserved; the list above identifies changes made for Software Discovery. The current packaging specification already includes the migration directory, so no packaging-spec edit was needed for this task.

## Database changes

Migration 002 advances `PRAGMA user_version` to 2 and adds `registered_applications` and `application_aliases`. Registrations contain stable `app-<UUID>` IDs, canonical paths, metadata, enabled/repair flags, and timestamps. Aliases have normalized uniqueness constraints and cascade on registration deletion. The unused legacy `applications` table remains for compatibility and never authorizes execution.

New and version-one databases migrate sequentially without editing 001. SQLite backups include registrations. Version-one backups migrate in memory before exact-schema validation; source backups remain unchanged. Integrity, foreign keys, exact schema, existing settings/assets/profile checks, DPAPI checks, application source/ID/path validation, and command target validation run before replacing live data. Missing executable registrations restore disabled with `needs_repair=1`. Unsafe registrations reject restore. Configuration imports append registrations, remap their IDs into imported commands, and disable missing paths. Existing conflicts still reject the whole import.

## Discovery sources

- `%APPDATA%/Microsoft/Windows/Start Menu/Programs`
- `%PROGRAMDATA%/Microsoft/Windows/Start Menu/Programs`
- HKCU Uninstall metadata.
- HKLM Uninstall metadata in the 64-bit Registry view.
- HKLM Uninstall metadata in the 32-bit/WOW6432 Registry view.
- Known PATH names only: `code.exe`, `git.exe`, `python.exe`, `node.exe`, `chrome.exe`.

Start Menu shortcuts use Windows `IShellLinkW` and `IPersistFile` through ctypes, consistent with [Microsoft's Shell link API](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-ishelllinkw). Discovery reads target, arguments, working directory, and optional icon metadata. It never executes a shortcut, invokes PowerShell, or calls Shell link Resolve to search for moved targets. Registry DisplayIcon values are parsed conservatively; uninstall strings and install directories never become launch targets. Entries without executable evidence remain diagnostic records requiring review.

Deduplication prioritizes canonical executable paths and file identity. Unambiguous metadata-only name matches merge metadata; different executable paths with the same name remain separate. Sources, publisher, version, and optional icon metadata are preserved. The merge caches path checks to avoid repeated filesystem work.

A real local scan found **281 candidates, 71 launchable**, with all six source types represented and no failed provider. The optimized scan took **2.5 seconds** on this machine; timings vary with installations and filesystem state. The initial implementation took about 10 seconds before repeated-path work was removed. Neither scan registered or executed anything.

## Security

V1 approval permits local `.exe` files only, with no shortcut arguments or inherited working directory. The shared denylist rejects CMD, PowerShell/pwsh, Registry tools, Windows scripting hosts, mshta/rundll32, scheduling/service/disk/shutdown tools, installer/update/uninstall/helper binaries, and additional administrative process hosts. Scripts and `.com`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.js`, `.dll`, and `.lnk` launch targets are unsupported. Relative, remote UNC/device, control-character, wildcard, quoted-command, and NTFS alternate-stream paths are rejected.

Approval revalidates the current executable rather than trusting a cached launchable flag. Launch resolves only built-in IDs or approved registration IDs; raw paths and unknown IDs are rejected. The launcher checks enabled/repair status, existence, type, denylist, and exact approved path again before `subprocess.Popen([path], shell=False)`. A newly substituted link/junction cannot redirect an approved path to another location. Missing executables fail with rediscovery guidance, with no PATH fallback or filename remapping for registered software.

All discovery is local. There are no network APIs, telemetry, online software lookups, or software-list uploads. Provider failures and scan logs contain source labels/counts rather than local paths. Existing phrase conflict checks, reserved memory behavior, negation veto, confidence threshold, history redaction, and HTTPS rules remain in the shared command pipeline.

## Smart Command integration

The existing RuleBasedIntentInterpreter receives live aliases from approved registrations. Simple open/launch/start command phrases also contribute target aliases; no application-specific parsing rule was added. The existing IntentResolver still resolves a registered command and enforces enabled/ambiguity/confidence rules. The resolved target is the stable application ID, not its display name or executable path.

Tests approve a simulated Spotify executable and verify `open spotify`, `launch spotify`, `can you start spotify`, `start spotify please`, and `spotify open pannu`. Custom phrases and edited aliases work through the same engine. Disabled registrations fail even when their command remains enabled. Removing registration disables associated commands and removes their dynamic aliases.

## Tests

Executed with `QT_QPA_PLATFORM=offscreen` using the project virtual environment:

```text
Existing tests: 444 passed
New tests:      100 passed
Total:         544 passed
Warnings:      1 existing speech_recognition/standard-aifc deprecation warning
```

The final complete run took 43.63 seconds. New tests include a real Windows COM shortcut round trip, malformed/broken source handling, all denylisted executable names, unsupported script types, Registry views, metadata-only entries, deduplication, approval persistence/rollback, editable UI approval/cancel, custom and Tanglish phrases, disabled/removed/missing registrations, final launcher revalidation, safe imports/restores, legacy migration/restore, background responsiveness, cancellation, shutdown, and worker failure.

The screenshot was rendered with native Windows fonts and visually checked. It uses simulated software records to avoid publishing the machine's installed-app list.

## Build verification

Application startup: **PASS** — final source self-test; report: `software-discovery-source-verification.json`.

Packaged build: **PASS** — final release generation and frozen self-test; report: `software-discovery-packaged-verification.json`. The executable archive was inspected to confirm it includes `validate_registered_path`, the final approval-path guard.

Installer: **PASS (payload verification)** — archive CRC, safe extraction, and the extracted application's complete self-test; report: `software-discovery-installer-verification.json` includes `installer_archive_verified=true`. The interactive installation flow was not run.

Final release artifacts:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `dist/v2/pet-animal/pet-animal.exe` | 15,110,778 | `3fa1979e04d94963c5910528bffad00f9751caf60fd3bbfb7fd25959e8a79504` |
| `dist/v2/Pet-Animal-2.0-Setup.exe` | 698,617,355 | `e750146b8bca0d06e764fcd60addfbab8cfa102faf62ac9af8a3833e7585ca3b` |

The application is a directory distribution: keep `pet-animal.exe` with its packaged `_internal` directory. Hashes and sizes are also saved in `software-discovery-artifact-hashes.json`.

Verification boundaries: external application launches are mocked in automated tests; no real third-party application was launched. A full interactive install/uninstall and microphone-hardware session were not performed. Microsoft Store apps, shortcut arguments, script targets, automatic refresh, repair/remapping, and icon extraction/cache are outside this V1 implementation. Optional icon metadata is collected, but executable icons are not extracted into a cache.
