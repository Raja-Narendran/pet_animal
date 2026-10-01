# One-click Software Discovery update

Verified on 2026-10-01, Windows 11, Python 3.14.3.

## Requested behavior

The user explicitly changed the original individual-approval requirement: clicking **Refresh Installed Software** now authorizes registration of every valid discovered application. No additional confirmation or individual Add click is required. Refresh never launches the detected applications.

The discovery worker remains read-only and runs in the background. Its results return to the Qt main thread, where `ApplicationCore.register_discovered_applications()` revalidates candidates, persists applications, and generates `open`, `launch`, and `start` phrases. Registration uses the existing transactional registration and conflict checks; UI listeners are notified once after the batch.

Repeated refreshes skip existing executable paths, preserve custom commands and disabled settings, and create a launch command for an existing registration that has no associated command. Conflicting aliases/phrases receive distinct names such as `spotify app` or `spotify app 2`. Built-in application aliases remain unambiguous. Invalid, unsupported, and dangerous targets remain excluded; final path revalidation and ID-only dispatch remain intact.

The UI explains the automatic behavior and reports added, existing, commands-created, invalid, and failed counts. Individual Add remains available for entries not added successfully. Registration failures are isolated so other valid entries can still be added.

## Changed files

- `src/core/application.py`: bulk registration, batched notifications, and collision-safe dynamic aliases.
- `src/app/software_discovery.py`: Refresh completion registers results and reports the summary; UI text describes automatic addition.
- `src/main.py`: source/frozen self-test verifies bulk registration and duplicate refresh.
- `tests/test_application_registration.py`: four new bulk-registration regressions.
- `tests/test_software_discovery_ui.py`: Refresh-button test verifies automatic registration, navigation responsiveness, no process launches, and idempotence.
- `README.md`: updated user workflow.
- This report, verification JSON files, release hashes, and the refreshed simulated UI screenshot.

No database migration or discovery-provider changes were needed.

## Actual verification

```text
Full regression suite: 548 passed
Targeted registration/UI/Smart Command suite: 120 passed
Existing warning: speech_recognition/standard-aifc deprecation
```

Real discovery results were registered in a temporary database with a mocked launcher; live application data was not modified:

```text
Candidates:             281
Valid applications:      71
First refresh added:     71
Launch commands created: 71
Invalid/skipped:        210
Registration failures:    0
Second refresh added:     0
Second refresh existing: 71
Applications launched:    0
Scan duration:          2.023 seconds
Registration duration:  1.383 seconds
```

Every generated command's first phrase resolved successfully through the command engine. See `software-discovery-auto-add-local-verification.json` for counts and timing.

Source startup/self-test: **PASS**, including bulk registration, duplicate refresh, Tanglish matching, disabled registrations, missing-path restore, and removal. Report: `software-discovery-auto-add-source-verification.json`.

Packaged application: **PASS**, including bulk registration and duplicate-refresh assertions. Report: `software-discovery-auto-add-packaged-verification.json`.

Installer: **PASS (payload verification)**, including CRC, extraction, and the extracted app's complete self-test. Report: `software-discovery-auto-add-installer-verification.json` records `installer_archive_verified=true`.

## Updated artifacts and packaging recovery

The initial standard-output build passed tests but could not replace a loaded `_audioop.pyd` in the running `dist/v2/pet-animal` distribution. The application was left running. Missing files from that interrupted cleanup were restored from the original installer after checking its previously recorded SHA-256; 28 missing files were restored, with existing files left untouched.

The final application and installer were successfully built in a separate output directory to avoid the running app's file locks:

- `dist/software-discovery-auto-add/pet-animal/pet-animal.exe`
- `dist/software-discovery-auto-add/Pet-Animal-2.0-Setup.exe`

Restart using the updated executable to receive the new behavior. Keep its packaged `_internal` directory alongside it. The existing running app was not replaced or restarted automatically.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Updated application executable | 15,114,260 | `82cf53c244b9169b0438e97ee474c00ca39a9ce400df6ae3a5ba4f920644dfca` |
| Updated installer | 698,620,564 | `44e76ec6aec1f19cca091cffad03923985c3ef60ca01f45494c961086639f7e4` |

Hashes are also saved in `software-discovery-auto-add-artifact-hashes.json`. The refreshed screenshot uses simulated application records and shows all entries marked Already Added after Refresh.

Verification boundaries: third-party process launches were mocked. An interactive install/uninstall and microphone-hardware session were not performed. The earlier `software-discovery-verification.md` documents the original per-app approval release; this report supersedes its refresh behavior and release results.
