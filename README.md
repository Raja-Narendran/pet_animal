# Pet Animal 2.0

A local Windows desktop companion with a Manager, a transparent floating husky, persistent memory, configurable command phrases, and pet profiles.

V2 extends this repository's working Python/PyQt6 application, as permitted by the supplied specification's existing-stack exception. Both windows use one Python application core and SQLite connection. There is no HTTP backend, AI provider, or text-to-speech. Microphone commands use a bundled multilingual Whisper model for Tamil and English; audio is never uploaded. Install the dependencies from requirements.txt to enable the microphone. Browser commands (`search <query>`, `play <song> on youtube`) run in background threads and require internet for the requested search/playback. YouTube opens in the default browser, with a search-page fallback if a direct video cannot be resolved. Selenium remains an optional service mode. These dependencies are included by the release specification.

## Run

```powershell
.venv\Scripts\python.exe src/main.py
```

For a fresh environment, use Python 3.10 or newer, create `.venv`, and install `requirements.txt`. Development currently includes legacy optional dependencies to keep the existing tests runnable. Prepare both offline speech models with the setup commands below; packaged releases include the speech engines and models.

## Use the app

- **Dashboard:** live memory and command counts, executions today, active pet, recent activity, and quick actions.
- **Memory:** add/edit/delete records; search titles, keys, descriptions and nonsensitive values; filter by database-backed categories; disable individual memories; import/export JSON. Memory keys are internal. Categories can optionally encrypt their values.
- **Commands:** configure multiple exact phrases per action, detect conflicts, enable/disable, edit, delete and test. Tests in the Manager execute the configured action.
- **Pet Studio:** select existing husky sheets or import a PNG sheet; create, edit and activate profiles; adjust size, desktop position, always-on-top, animation, and chat appearance. Preview changes before saving. Saving updates the floating pet immediately.
- **Activity:** filter executions by command, status or local date. Clear history with confirmation.
- **Settings:** persist theme, tray, notifications, Manager minimization and whether the pet opens when the app starts; import/export configuration; create/restore database backups; open logs; explicitly quit.

Close the Manager to leave the floating pet running. Reopen it through **Open Manager** in the tray. With the tray disabled, hiding the pet opens the Manager so there is always a way back. Closing the Manager when both the pet and tray are hidden exits. The pet's × control hides the pet. **Quit** ends the application.

## Command patterns

Commands normalize case and whitespace, then match registered phrases exactly. The initial actions open Chrome, Calculator, Notepad, Explorer, VS Code, Google and YouTube. Application actions accept only the existing native launcher's five allowlisted application IDs. Website actions accept registered HTTPS URLs without credentials. The app never executes raw input as a shell command.

The following deterministic patterns are reserved:

```text
help
remember my name as Naren
what is my name
```

A `remember` command proposes the value and displays a Yes/No confirmation before saving `user.name`. Repeating it updates the same record. Cancel leaves memory unchanged. Memory commands do not enter command history. Unsupported input is recorded only as `[unsupported command]`.

## Storage and privacy

The application stores data in `%LOCALAPPDATA%\PetAnimal`:

```text
database/petanimal.db
pets/imported/
backups/
logs/
state.json
```

Sensitive-category values use Windows DPAPI encryption tied to the current Windows user. Listings mask values, search does not decrypt them, and ordinary memory exports exclude sensitive categories. Edit/reveal is an explicit local UI action. Only the value is encrypted: titles and descriptions should not contain passwords or card numbers. Name and other ordinary categories are plain structured SQLite data.

Schema migrations are versioned under `src/database/migrations`. Foreign keys, uniqueness constraints and indexes are enabled. Imports validate records and reject conflicts transactionally rather than silently overwriting existing records. Configuration imports append commands and profiles, apply imported preferences, and activate the imported active profile. An export containing phrases already registered on this installation will be rejected; remove those records from the JSON before an additive import.

Database backups use SQLite's backup API. Restore requires confirmation, validates integrity/schema/actions/settings/assets, and creates a recovery backup before replacement. Backups retain encrypted values and require the original Windows user for decryption. A database backup does not embed imported PNGs: keep `pets/imported` alongside your backups; restore rejects missing assets. Windows login autostart is not configured; the startup preference controls what happens when Pet Animal itself starts.

## Development and verification

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe src/main.py --self-test build/source-verification.json
```

The self-test uses a temporary database, performs no application launches, and checks migration, memory, restore, all six pages, live profile switching, independent Manager closing and quit cleanup. Tests mock external launches and do not require Chrome or VS Code.

The UI uses the requested palette and local icons fetched from the supplied Figma reference. It adapts the design to native Qt layouts and replaces sample AI/workspace activity with actual application data. Existing sprite sheets are reused without generating new images.

## Windows release

```powershell
.\release\build.ps1
```

This runs tests, builds the native application, embeds it in a Windows installer and writes:

```text
dist/v2/pet-animal/pet-animal.exe
dist/v2/Pet-Animal-2.0-Setup.exe
```

The installer installs for the current Windows user under `%LOCALAPPDATA%\Programs\Pet Animal`, creates a Start menu shortcut, and registers uninstall in Windows Settings. It needs no administrator access. Quit the app before uninstalling. Uninstallation preserves `%LOCALAPPDATA%\PetAnimal` and all saved memories. Existing installations are not overwritten; uninstall the previous app first. The executable and installer are unsigned.

The build preserves the existing V1 output under `dist/pet-animal`. Build resources include the migration, original pet sheets and local design icons.

## Architecture

```text
ManagerWindow ─┐
               ├── ApplicationController ── ApplicationCore ── SQLite
PetWindow ─────┘                                  │
                                      validated WindowsLauncher
```

`ApplicationCore` exposes UI-independent memory CRUD/retrieval, exact phrase registration/execution, profile/settings management, imports and backups. `ApplicationController` owns window lifecycle and live propagation. Native OS calls are confined to the validated launcher. DPAPI is isolated in `src/core/secrets.py`. Future providers should call the same restricted core rather than executing operating-system requests themselves.

See `docs/verification.md` for release validation and remaining verification boundaries.

Local voice recognition uses the bundled multilingual Whisper small model on CPU (int8). Click the microphone to switch the chat input into a live speech bar with an audio-driven waveform. The recognized text appears after you finish speaking. Cancel restores the typed input; successful speech runs through voice-specific command matching, and failed commands retain their text for correction. Registered phrases, including disabled phrases, take precedence over browser shortcuts. Free-form browser queries and song titles are omitted from persistent command history.

Prepare the local model when setting up a fresh checkout (download occurs only during setup/build, never while listening):

```powershell
.venv\Scripts\python.exe release/prepare_voice_model.py
.venv\Scripts\python.exe release/prepare_multilingual_voice.py
```

The release bundles the model. Spoken application aliases such as “open Google Chrome” and “open note pad” resolve to enabled registered commands. Typed phrases still match exactly. Audio remains in memory and is discarded after each utterance. Recognition works offline; requested YouTube playback/web search still requires internet.

Voice commands wait for at least 1.5 seconds of trailing silence before execution. Short pauses stay within the same command. The 60-second recording safety limit rejects an incomplete command instead of executing it.

Tamil and English can be mixed in voice commands, for example:

- `Shape of You பாட்டு play பண்ணு` → play Shape of You on YouTube.
- `Chrome open பண்ணு` or `குரோம் ஓபன் பண்ணுங்க` → open Chrome.
- `வாத்தி கம்மிங் பாட்டு போடு` → search/play the Tamil song title.
- `சென்னை weather search பண்ணு` → search the mixed-language query.

Recognition automatically detects the spoken language and transcribes it without translation. English brand/song names can remain in English or use the explicit Tamil aliases. Command matching supports the documented Tamil/Tanglish verbs rather than arbitrary natural-language requests. The waveform follows live microphone audio; the bar shows **Recognizing…** during local processing, which can take several seconds on CPU. Cancel suppresses late results. Typed matching and disabled/custom-command precedence remain unchanged.

The multilingual model is pinned to a verified [faster-whisper small revision](https://huggingface.co/Systran/faster-whisper-small/tree/536b0662742c02347bc0e980a01041f333bce120). Setup downloads about 486 MB; listening never accesses the model hub or uploads audio. The legacy English Vosk path remains available to developers with `VOICE_MULTILINGUAL=False`.

See [docs/structure-audit.md](docs/structure-audit.md) for the file tree, entry points, dependency audit, cleanup decisions and current packaging gaps.
