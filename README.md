# Pet Animal 2.0

An offline, local-first, privacy-focused Windows desktop companion featuring a transparent floating Husky pet, an interactive command bar with `@` application autocomplete, bundled multilingual speech recognition (English + Tamil + Tanglish), persistent personal memory with Windows DPAPI encryption, software discovery, and a full-featured 6-page native Manager window.

Pet Animal 2.0 runs natively on Windows with Python and PyQt6. Both windows share a single headless application core and local SQLite database. The entire application operates completely offline without external HTTP backends, cloud telemetry, or remote AI APIs.

---

## Table of Contents

- [Overview & Architecture](#overview--architecture)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Local Installation](#local-installation)
  - [Running the Companion](#running-the-companion)
  - [Offline Voice Model Setup](#offline-voice-model-setup)
- [Floating Desktop Companion](#floating-desktop-companion)
  - [Interactive Sprite & States](#interactive-sprite--states)
  - [Desktop Anchoring & Movement](#desktop-anchoring--movement)
  - [Minimize & Restore](#minimize--restore)
  - [Response Speech Balloon](#response-speech-balloon)
  - [System Tray & Safe Exit](#system-tray--safe-exit)
- [Command Bar & `@` Shortcut Autocomplete](#command-bar---shortcut-autocomplete)
- [Offline Multilingual Voice Recognition](#offline-multilingual-voice-recognition)
  - [Supported Languages & Code-Mixing](#supported-languages--code-mixing)
  - [Waveform & Voice Bar Controls](#waveform--voice-bar-controls)
  - [Privacy & Silence Detection](#privacy--silence-detection)
- [Native Manager Window](#native-manager-window)
  - [1. Dashboard](#1-dashboard)
  - [2. Memory Engine](#2-memory-engine)
  - [3. Commands & Intent Manager](#3-commands--intent-manager)
  - [4. Pet Studio](#4-pet-studio)
  - [5. Activity Audit Log](#5-activity-audit-log)
  - [6. Settings](#6-settings)
- [Software Discovery & One-Click Refresh](#software-discovery--one-click-refresh)
- [Smart Command Pipeline](#smart-command-pipeline)
  - [Execution Flow](#execution-flow)
  - [Negation Veto](#negation-veto)
  - [Reserved Memory & Help Phrases](#reserved-memory--help-phrases)
  - [Confidence Gating & Clarification](#confidence-gating--clarification)
  - [Web Search & YouTube Playback](#web-search--youtube-playback)
- [Storage, Privacy & Security Invariants](#storage-privacy--security-invariants)
  - [Local Storage Layout](#local-storage-layout)
  - [Windows DPAPI Encryption](#windows-dpapi-encryption)
  - [History & Logging Privacy](#history--logging-privacy)
  - [Safe Database Backup & Restore](#safe-database-backup--restore)
  - [Zero Shell Execution Guarantee](#zero-shell-execution-guarantee)
- [Development, Testing & Verification](#development-testing--verification)
  - [Automated Test Suite (774 Tests)](#automated-test-suite-774-tests)
  - [Headless Diagnostic Self-Test](#headless-diagnostic-self-test)
  - [Packaging the Windows Release & Installer](#packaging-the-windows-release--installer)
  - [Release Artifact Verification](#release-artifact-verification)

---

## Overview & Architecture

Pet Animal 2.0 enforces a strict two-tier architecture separating the domain logic from presentation widgets:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          Presentation Tier                             │
│   ┌───────────────────────────────┐  ┌─────────────────────────────┐   │
│   │         ManagerWindow         │  │          PetWindow          │   │
│   │    (6 Administration Tabs)    │  │  (Floating Transparent Pet) │   │
│   └───────────────┬───────────────┘  └──────────────┬──────────────┘   │
└───────────────────┼─────────────────────────────────┼──────────────────┘
                    │                                 │
┌───────────────────▼─────────────────────────────────▼──────────────────┐
│                         ApplicationController                          │
│   - Window lifecycle, visibility, tray icon, & minimization            │
│   - Real-time appearance synchronization & position persistence        │
│   - Asynchronous worker coordination (voice, browser, discovery)       │
│   - Application shortcut (@) autocomplete popover coordination         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    ApplicationCore (Headless Domain)                   │
│   - Pure Python & SQLite 3 (Zero GUI / Qt / HTTP dependencies)         │
│   - Personal Memory Engine (Typed records, retrieval, DPAPI masking)   │
│   - Smart Command Interpreter & Intent Resolver                        │
│   - Software Discovery & Registration Service                          │
│   - Pet profile validation & appearance settings                       │
│   - SQLite backup, restore & cryptographic validation                  │
└─────────────────┬──────────────────────────────────┬───────────────────┘
                  │                                  │
┌─────────────────▼─────────────┐    ┌───────────────▼──────────────┐
│        SQLite Database        │    │        WindowsLauncher       │
│  - WAL mode, foreign keys     │    │  - Strict allowlist dispatch │
│  - Migrations (v1 to v5)      │    │  - No shell=True execution   │
│  - DPAPI ciphertext storage   │    │  - HTTPS URL validation      │
└───────────────────────────────┘    └──────────────────────────────┘
```

- **Headless Domain (`src/core/application.py`)**: Central domain controller containing pure Python business logic, SQLite query routines, schema migrations, and listener callbacks.
- **Application Controller (`src/app/controller.py`)**: Coordinates window lifecycles, manages desktop positioning, synchronizes theme/appearance mutations, and routes commands.
- **Presentation Windows (`src/app/`)**: `PetWindow` (the desktop companion) and `ManagerWindow` (the management studio).
- **Execution Services (`src/services/`)**: `WindowsLauncher` for allowlisted application and URL dispatch, `VoiceInputWorker` for offline speech transcription, and `SoftwareDiscoveryService` for Start Menu and registry scanning.

---

## Quick Start

### Prerequisites
- **Operating System**: Windows 10 or Windows 11 (64-bit).
- **Python**: Python 3.10 to Python 3.14.
- **Microphone**: Any standard audio input device for voice recognition.

### Local Installation
Clone the repository and set up a virtual environment:

```powershell
# Clone the repository
git clone https://github.com/Raja-Narendran/pet_animal.git
cd pet_animal

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install required dependencies
pip install -r requirements.txt
```

### Running the Companion
Launch the application:

```powershell
.venv\Scripts\python.exe src/main.py
```

- If `launch_pet` is `True` in settings, the transparent floating Husky companion appears on your desktop.
- If `start_minimized` is `False` or the system tray is hidden, the native **Manager Window** opens automatically.
- Logs are written to `%LOCALAPPDATA%\PetAnimal\logs\pet_animal.log`.

### Offline Voice Model Setup
Pet Animal bundles models in release packages. For local development on a fresh checkout, run the model preparation scripts once:

```powershell
# 1. Download Vosk English speech model (~40 MB)
.venv\Scripts\python.exe release/prepare_voice_model.py

# 2. Download faster-whisper small multilingual model (~486 MB for Tamil + English)
.venv\Scripts\python.exe release/prepare_multilingual_voice.py
```

> [!NOTE]
> Downloads occur strictly during setup and build. At runtime, the models run 100% offline on your CPU with zero internet connectivity.

---

## Floating Desktop Companion

The companion window (`PetWindow`) provides an interactive desktop presence:

![Floating Pet](docs/screenshots/floating-pet.png)

### Interactive Sprite & States
The Husky companion features animated pixel-art sprites rendered using transparent frames (`WA_TranslucentBackground`):
- **Idle**: Gentle breathing/blinking idle animation.
- **Greeting**: Interactive tail-wagging greeting triggered whenever you click the pet.
- **Thinking**: Displayed while listening to microphone input or parsing a command.
- **Working**: Animated during background command execution, search, or YouTube resolution.
- **Sleeping**: Calming sleep state accessible via right-click context menu.
- **Success**: Cheerful reaction upon successful command execution.
- **Error**: Expressive error animation if a command fails or is rejected.

### Desktop Anchoring & Movement
- **Draggable Positioning**: Click and drag the pet anywhere on your multi-monitor desktop.
- **Persistent Coordinates**: Screen coordinates are automatically saved to `%LOCALAPPDATA%\PetAnimal\state.json` and synced to the active pet profile.
- **Screen Boundary Clamping**: The window automatically detects monitor bounds and keeps controls accessible above the taskbar.
- **Anchor Invariant**: Opening the command box, displaying response balloons, or switching states maintains the pet's screen position without shifting or jumping.

### Minimize & Restore
- **Minimize Pet (`−`)**: Clicking the minimize button in the control bar collapses the pet companion while keeping the compact command chat box on screen.
- **Expand Pet (`▲`)**: Clicking the expand arrow on the chat box smoothly restores the pet companion and control bar.

### Response Speech Balloon
The response bubble (`ResponseBubbleWidget`) is a standalone floating window that appears directly above the companion:
- Displays command confirmations, query answers, and status messages.
- Custom-painted antialiased rounded background and soft shadow (eliminating Qt translucent window ghosting).
- Auto-hides after a configurable timeout (default: 3 seconds for results, 4 seconds for errors).
- Doubles as the interactive `@` shortcut suggestion popover.

### System Tray & Safe Exit
- **System Tray Icon**: Lives in the Windows notification area with a context menu (`Show Floating Pet`, `Open Manager`, `Hide Floating Pet`, `Settings`, `Quit`). Double-clicking opens the Manager.
- **Lockout Prevention**: If you hide the pet companion while the system tray icon is disabled in Settings, the Manager automatically opens so you are never locked out of the application.
- **Closing the Pet (`×`)**: Hides the companion. If tray notifications are enabled, a balloon confirms the pet is resting.
- **Exit Pet Animal**: Gracefully shuts down background workers, stops animations, saves coordinates, and terminates the Qt event loop.

---

## Command Bar & `@` Shortcut Autocomplete

The command input bar (`CommandBoxWidget`) provides semi-transparent glass styling with custom-rendered rounded corners and subtle drop shadows:

- **Direct Command Input**: Type any command phrase and press <kbd>Enter</kbd> or click <kbd>➤</kbd>.
- **`@` Shortcut Autocomplete**:
  - Type `@` to instantly open a floating suggestion balloon above the companion showing all enabled registered applications.
  - Continue typing (e.g. `@ch`, `@spot`, `@code`) to filter suggestions in real time.
  - Navigate suggestions using the <kbd>↑</kbd> and <kbd>↓</kbd> arrow keys.
  - Press <kbd>Enter</kbd>, click <kbd>➤</kbd>, or click an item directly to launch the application.
  - Press <kbd>Esc</kbd> to dismiss suggestions.
  - Works seamlessly in both full companion mode and minimized chat-only mode.
  - **Live Authorization**: Suggestion entries use stable IDs (`app-<uuid>`) and revalidate the executable path on every launch; typing alone never executes arbitrary code.

---

## Offline Multilingual Voice Recognition

Clicking the microphone icon (`🎤`) transforms the text input into an audio-driven speech bar.

### Supported Languages & Code-Mixing
Pet Animal uses a pinned [faster-whisper small](https://huggingface.co/Systran/faster-whisper-small) model running on CPU with 8-bit quantization (`int8`):
- **English**: `open Chrome`, `launch Calculator`, `search Google for Python tutorials`, `play Shape of You on YouTube`.
- **Tamil**: `குரோம் ஓபன் பண்ணுங்க`, `சென்னை வானிலை தேடு`, `வாத்தி கம்மிங் பாட்டு போடு`.
- **Tanglish (Code-Mixed Tamil + English)**:
  - `Chrome open பண்ணு` or `Chrome ah open pannu` → opens Google Chrome.
  - `Shape of You பாட்டு play பண்ணு` or `Shape of You paattu play pannu` → plays Shape of You on YouTube.
  - `vs code start பண்ணு` → opens Visual Studio Code.
  - `சென்னை weather search பண்ணு` → searches Chennai weather.

### Waveform & Voice Bar Controls
- **Audio Waveform (`AudioWaveform`)**: Renders real-time animated waveform bars responsive to live microphone PCM amplitude.
- **Status Indicators**: Displays progressive state transitions: `Starting…` → `Listening…` → `Recognizing…`.
- **Dedicated Cancel Button (`×`)**: Immediately halts audio recording, frees workers, and restores text input without executing.
- **Correction Preservation**: If a spoken command fails or is unrecognized, the transcribed text is retained in the text input box so you can edit and submit it manually without speaking again.

### Privacy & Silence Detection
- **Local Audio Processing**: Audio is processed entirely in RAM and immediately discarded after recognition; zero bytes are uploaded or saved to disk.
- **WebRTC VAD Silence Detection**: Automatically detects when you stop speaking (1.5 seconds of trailing silence) to trigger recognition.
- **Safety Cutoff**: A 60-second phrase limit automatically discards incomplete recordings rather than executing unintended commands.

---

## Native Manager Window

The Manager Window (`ManagerWindow`) provides a native desktop interface with six specialized administration pages built with Figma-inspired design tokens:

![Dashboard](docs/screenshots/dashboard.png)

### 1. Dashboard
- **Live Metrics**: Real-time counters showing total saved memories, registered commands, and executions today.
- **Active Pet Profile**: Displays active pet name, dimensions, sprite preview, and status.
- **Quick Action Buttons**: Instant access to Add Memory, New Command, Customize Pet, Backup Database, and Open Floating Pet.
- **Recent Activity Audit Feed**: Chronological log of recent executions with timestamps and success/failure indicators.
- **Category Progress Bars**: Visual breakdown of stored memories by category.

---

### 2. Memory Engine

![Memory Manager](docs/screenshots/memory.png)

Manage persistent structured memories with Windows DPAPI encryption:
- **Record Types**: `PROFILE`, `PREFERENCE`, `KNOWLEDGE`, `HABIT`, `RELATIONSHIP`, `NOTE`, `CONTEXT`, and `SYSTEM`.
- **Record Scopes**:
  - `GLOBAL`: Available system-wide.
  - `PROFILE`: Bound to the current user profile.
  - `PET_PROFILE`: Bound to the active pet companion profile.
  - `SESSION`: Ephemeral records cleared automatically on application restart or shutdown.
  - `TEMPORARY`: Time-limited records that expire after a specified duration.
- **Simplified Categories**:
  - `Personal Information` (Unencrypted structured data: Name, Address, IDs, Mobile, Email).
  - `Password` (Sensitive: encrypted via Windows DPAPI).
  - `Credit and Debit card details` (Sensitive: encrypted via Windows DPAPI).
  - `Important Notes` (General notes and project context).
- **Add Memory Dialog**:
  - Pre-filled personal title selectors: **Name**, **Address**, **IDs** (with dynamic ID title input, e.g. Passport, License), **Mobile number**, **Email ID**, or **Custom**.
  - Password category automatically prompts for **Website or app name** and generates standard keys (`<app>.password`).
- **DPAPI Protection**:
  - Sensitive categories store base64-encoded Windows DPAPI ciphertexts (`dpapi:<base64>`).
  - Values are masked as `••••••••` in tables, search results, and logs.
  - Click **Reveal encrypted value** to temporarily decrypt and view records locally.
- **Tags, Aliases & Relationships**:
  - Add search tags and multiple trigger aliases (e.g. `user.name` aliased to `my name`, `user name`).
  - Create directed graph relationships between memories (e.g., `preferred.editor` *used_for* `project.pet_animal.path`).
- **Lifecycle & Maintenance**:
  - **Clean Expired Memories**: Filters and purges expired temporary memories with user confirmation.
  - **Safe Export**: Exports non-sensitive memories and relationships to JSON (sensitive records are strictly excluded).
  - **Import Memories**: Validates JSON memory payloads with full duplicate and conflict preview before committing.
  - **Full Encrypted Backup**: Creates a complete SQLite database backup preserving DPAPI ciphertexts.

---

### 3. Commands & Intent Manager

![Commands Manager](docs/screenshots/commands.png)

Configure, audit, and test application and URL commands:
- **Command Registry**: Table listing command name, action type (`application` or `url`), target ID/URL, configured phrases (1–30 phrases per command), and enabled status.
- **Actions**: Add new commands, edit existing commands, delete custom commands, toggle enabled/disabled, and run **Test selected**.
- **Smart Command Tester ("Test Understanding")**:
  - Tests how Pet Animal understands a typed or spoken phrase without executing it or recording history.
  - Reports matched intent type, action type, target ID, resolved registered phrase, confidence score, match reason, and negation status.
- **Software Discovery Panel**: Access the background discovery scanner and application alias manager (detailed below).

---

### 4. Pet Studio

![Pet Studio](docs/screenshots/pet-studio.png)

Customize your desktop companion's appearance and behavior:
- **Builtin Sprite Sheets**: Select from builtin Husky states (`idle`, `greeting`, `thinking`, `working`, `sleeping`, `success`, `error`).
- **Import Custom Sprite Sheets**: Import your own PNG sprite sheets (validates $\le 8\text{ MB}$, square frames from 16px to 512px height, horizontal strip of 1–64 frames).
- **Profile Management**: Create, edit, switch, and delete pet profiles (enforces exactly one active profile).
- **Live Appearance Sliders**:
  - **Companion Size**: 96 px to 400 px.
  - **Chat Bubble Width**: 260 px to 600 px.
  - **Input Text Font Size**: 10 px to 24 px.
  - **Corner Radius**: 0 px to 30 px.
  - **Glass Background Opacity**: 20% to 100%.
  - **Background Color**: Hex color code picker.
  - **Toggles**: Always on Top, Enable Animations.
- **Interactive Live Preview**: Real-time mockup showing the sprite animation and chat box styling before saving.

---

### 5. Activity Audit Log

![Activity Log](docs/screenshots/activity.png)

A comprehensive, privacy-preserving audit log of all command executions:
- **Columns**: Timestamp, Command Name, Trigger Phrase, Execution Status (`success` / `failed`), Error Details.
- **Filtering**: Filter by execution status (`All`, `Success`, `Failed`), command selection, or specific local calendar date.
- **Clear History**: Purges all execution history with user confirmation.
- **Privacy Protections**: Unsupported inputs are logged strictly as `[unsupported command]`. Free-form search queries and song titles are logged only as `[web search]` or `[music playback]`. Password contents and memory values never enter execution history.

---

### 6. Settings

![Settings](docs/screenshots/settings.png)

Application preferences and database maintenance:
- **Appearance**: Toggle between **Light Theme** and **Dark Theme**.
- **Startup & Windows Behavior**:
  - `Launch floating pet on startup`: Automatically shows the pet companion on boot.
  - `Start minimized to system tray`: Launches directly to tray without opening the Manager.
  - `Show system tray icon`: Toggles system tray integration.
  - `Enable desktop notifications`: Enables balloon notifications for background events.
- **Voice Recognition Mode**:
  - `Offline English (Vosk)`: Lightweight CPU speech recognition with streaming partial words.
  - `Multilingual Offline (Whisper Small)`: Bundled neural model for English, Tamil, and Tanglish.
- **Storage & Diagnostics**:
  - **Open Logs Folder**: Opens `%LOCALAPPDATA%\PetAnimal\logs` in File Explorer.
  - **Export Configuration**: Saves settings, commands, profiles, and registered applications to JSON.
  - **Import Configuration**: Validates and imports configuration JSON.
  - **Create Database Backup**: Creates an instantaneous SQLite backup snapshot in `%LOCALAPPDATA%\PetAnimal\backups\`.
  - **Restore Database**: Validates SQLite integrity, foreign keys, schema matching, asset existence, and DPAPI decryption before restoring.
- **Quit Pet Animal**: Explicit application exit button.

---

## Software Discovery & One-Click Refresh

![Software Discovery](docs/screenshots/software-discovery.png)

The Software Discovery engine automatically finds installed Windows applications without manual path entry:

- **Discovery Providers**:
  - **User & System Start Menus**: Scans `.lnk` shortcuts from `%APPDATA%\Microsoft\Windows\Start Menu` and `%PROGRAMDATA%\Microsoft\Windows\Start Menu`.
  - **Windows Uninstall Registry**: Scans 32-bit and 64-bit registry keys (`HKCU` and `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall`).
  - **System PATH**: Resolves known common executables on `PATH`.
- **One-Click "Refresh Installed Software"**:
  - Click **Refresh Installed Software** in **Commands → Discover Software** to scan all providers in a non-blocking background worker.
  - Automatically filters out uninstallers, updaters, helper binaries, scripts (`.bat`, `.cmd`, `.ps1`), and administrative tools.
  - Automatically registers all valid launchable applications with standard `open <app>`, `launch <app>`, and `start <app>` command phrases.
  - Generates unique aliases for duplicate names (e.g. `spotify app`, `spotify app 2`).
  - Skips already-registered software and preserves disabled commands.
  - Displays a summary dialog with counts of added, already existing, invalid, and failed applications.
- **Candidate Filtering**: Filter candidate lists by **All**, **Launchable**, **Already Added**, **Review Needed**, or **Invalid**.
- **Manual Registration**: Individual **Add to Pet Animal** dialog allows customizing the application display name, trigger aliases, and command phrases.
- **Application Management**:
  - View registered applications, their executable paths, discovery sources, and repair status.
  - Toggle enabled/disabled.
  - Edit application trigger aliases.
  - Unregistering disables associated command phrases while keeping installed files intact.
- **Repair Status**: If a registered executable is moved or deleted, the application is marked as **Needs repair** and disabled to prevent unsafe launches.

---

## Smart Command Pipeline

### Execution Flow

Every command (typed, transcribed, or submitted via `@` shortcut) passes through a multi-tier deterministic pipeline:

```text
User Input (Typed or Spoken)
  │
  ├─► [1] Input Validation (≤ 500 chars, no control characters)
  │
  ├─► [2] Mandatory Negation Veto (e.g. "don't open chrome" ➔ CANCELLED)
  │
  ├─► [3] '@' Application Shortcut (Direct lookup of registered application)
  │
  ├─► [4] Reserved Phrases Check (help, name storage, memory commands)
  │
  ├─► [5] Exact Registered Phrase Match (SQLite registered command phrases win)
  │
  ├─► [6] Multilingual / Tanglish Voice Normalization
  │
  ├─► [7] Rule-Based Intent Interpretation (Verbs: open, launch, search, play)
  │
  ├─► [8] Live Intent Resolver (Matches enabled commands & aliases)
  │
  ├─► [9] Confidence Gate (≥ 0.85 auto-executes; < 0.85 prompts clarification)
  │
  └─► [10] Safe Launcher Execution (Validated WindowsLauncher or Background Worker)
```

### Negation Veto
Pet Animal enforces a mandatory safety veto: any command containing negation words (e.g., `do not`, `don't`, `never`, `vendam`, `koodadhu`) is immediately halted with:
> *"Command cancelled. Nothing was executed."*

The negation veto takes precedence over everything, including exact registered custom phrases.

### Reserved Memory & Help Phrases

The following deterministic patterns are reserved:

| Pattern | Action |
| :--- | :--- |
| `help` / `show help` / `commands` / `?` | Displays supported commands and usage syntax. |
| `remember my name as <value>` | Proposes saving your name; displays Yes/No confirmation dialog. |
| `save my name as <value>` | Proposes saving your name with Yes/No confirmation. |
| `my name is <value>, remember that` | Proposes saving your name with Yes/No confirmation. |
| `what is my name` / `do you remember my name` | Retrieves and displays your saved name. |
| `remember <key> as <value>` | Proposes saving a memory record with Yes/No confirmation. |
| `save <key> as <value>` | Proposes saving a memory record with Yes/No confirmation. |
| `remember that <key> is <value>` | Proposes saving a memory record with Yes/No confirmation. |
| `remember note: <text>` | Saves an important note record with Yes/No confirmation. |
| `what is <key>` / `what's <key>` / `recall <key>` | Queries and displays the requested structured memory record. |
| `what browser do i prefer` | Queries your saved `preferred.browser` preference. |
| `open my browser` | Resolves `preferred.browser` and launches the preferred application. |
| `open my editor` | Resolves `preferred.editor` and launches your preferred code editor. |
| `forget <key>` / `delete memory <key>` | Displays Yes/No confirmation to delete the specified memory record. |

> [!IMPORTANT]
> Memory proposals expire after 5 minutes if unconfirmed. Confirmed memory commands and their values never enter command history.

### Confidence Gating & Clarification
- Matches with confidence $\ge 0.85$ execute automatically.
- Matches with ambiguous targets (multiple matching enabled commands) or confidence below $0.85$ prompt for clarification (e.g. `open code` returns *"Did you mean 'Open VS Code'?"*).
- Unknown commands return *"Unsupported command. Type help to see registered phrases."*

### Web Search & YouTube Playback
- **Web Search**: `search Google for <query>`, `search for <query>`, `look up <query>`.
  - Opens Google Search in your default browser.
  - Requires an enabled registered `google` URL command.
  - Runs in a background worker (`BrowserWorker`) to prevent UI freezing.
- **YouTube Music Playback**: `play <song> on youtube`, `play song <song>`, `<song> பாட்டு play பண்ணு`.
  - Searches and plays the requested video on YouTube.
  - Requires an enabled registered `youtube` URL command.
  - Runs in an asynchronous worker (`YouTubePlayWorker`).
  - Free-form search queries and song titles are masked in command history as `[web search]` and `[music playback]`.

---

## Storage, Privacy & Security Invariants

### Local Storage Layout
All runtime data is stored locally in `%LOCALAPPDATA%\PetAnimal`:

```text
%LOCALAPPDATA%\PetAnimal\
├── database\
│   └── petanimal.db         # Primary SQLite 3 database (WAL mode, foreign keys, user_version 5)
├── pets\
│   └── imported\            # User-imported PNG sprite sheets (<uuid>.png)
├── backups\                 # Online SQLite backup snapshots (petanimal-YYYYMMDD-HHMMSS-*.db)
├── logs\
│   └── pet_animal.log       # Rotating operational log file
└── state.json               # Window coordinates and UI visibility cache
```

### Windows DPAPI Encryption
- Sensitive categories (`Password`, `Credit and Debit card details`) encrypt values using Windows Data Protection API (`crypt32.dll` via `ctypes`).
- Ciphertexts are stored as `dpapi:<base64-string>`. No encryption keys are stored on disk.
- Encryption is cryptographically bound to the active Windows user account security identifier (SID).
- Sensitive values are masked (`••••••••`) across listings, tables, search results, and logs.
- Plain memory JSON exports completely omit sensitive records.
- Values are only decrypted when an authorized user explicitly clicks **Reveal encrypted value** in the Manager UI.

### History & Logging Privacy
- Unsupported inputs are recorded strictly as `[unsupported command]`. Raw invalid inputs are never stored to prevent leaking mistyped credentials.
- Free-form browser queries and song titles are logged only as `[web search]` or `[music playback]`.
- Memory storage and query commands bypass command history entirely.

### Safe Database Backup & Restore
Backups are created using SQLite's online backup API (`db.backup()`). Restoring a database validates:
1. SQLite integrity check (`PRAGMA integrity_check == 'ok'`).
2. Foreign key consistency (`PRAGMA foreign_key_check`).
3. Schema parity (matches runtime tables, constraints, and indexes; prevents SQL injection).
4. Command validation (all actions and application IDs are valid).
5. Active pet profile (exactly one active profile).
6. Sprite asset existence (all referenced PNGs exist on disk).
7. DPAPI decryption test (ensures sensitive records can be decrypted by the current Windows user).
8. Automatic pre-restore recovery snapshot (creates a recovery backup before replacing live data).

### Zero Shell Execution Guarantee
- **No Shell Execution**: The application never invokes `subprocess.Popen(..., shell=True)` or `os.system()`.
- **Argument List Execution**: Applications must be registered in `WindowsLauncher.SUPPORTED_APPS` or validated in `registered_applications` with an absolute path to a local `.exe` file.
- **URL Validation**: Web actions only accept valid `https://` URLs without embedded credentials (`user:pass@`) on standard port 443.

---

## Development, Testing & Verification

### Automated Test Suite (774 Tests)
Pet Animal 2.0 includes a comprehensive test suite covering all modules:

```powershell
# Run the complete test suite
.venv\Scripts\python.exe -m pytest -q
```

**Expected Result**:
```text
774 passed, 1 warning in ~65s
```

Run targeted test modules during focused development:

```powershell
# Core domain & SQLite tests
.venv\Scripts\python.exe -m pytest tests/test_application_core.py -q

# Personal Memory Engine tests
.venv\Scripts\python.exe -m pytest tests/test_memory_engine.py tests/test_memory_commands.py tests/test_memory_ui.py -q

# Smart command interpreter & normalizer
.venv\Scripts\python.exe -m pytest tests/test_smart_commands.py tests/test_command_interpreter.py -q

# Software discovery service & UI
.venv\Scripts\python.exe -m pytest tests/test_software_discovery.py tests/test_software_discovery_ui.py -q

# Application shortcuts & autocomplete
.venv\Scripts\python.exe -m pytest tests/test_application_shortcuts.py -q

# Multilingual voice recognition
.venv\Scripts\python.exe -m pytest tests/test_multilingual_voice.py tests/test_voice_bar.py -q

# Windows launcher & security checks
.venv\Scripts\python.exe -m pytest tests/test_windows_launcher.py -q
```

### Headless Diagnostic Self-Test
The application features a built-in offscreen verification mode (`--self-test`) that creates a temporary isolated environment to verify database migrations, memory persistence, backup/restore, software discovery, all six Manager pages, live profile switching, speech engines, and clean shutdown without displaying GUI windows:

```powershell
.venv\Scripts\python.exe src/main.py --self-test build/source-verification.json
```

Inspect the generated JSON report:

```powershell
Get-Content build/source-verification.json | ConvertFrom-Json
```

Expected result:
```json
{
  "success": true,
  "version": "2.0.0",
  "software_discovery": {
    "candidates": 281,
    "launchable": 71
  },
  "personal_memory_engine": {
    "schema_version": 5,
    "preference_resolution": true,
    "aliases_tags_relationships": true,
    "access_tracking": true,
    "dpapi_safe_export": true,
    "session_restore_cleanup": true
  },
  "checks": [
    "SQLite migration",
    "memory persistence",
    "backup restore",
    "six Manager pages",
    "live profile switching",
    "independent Manager closing",
    "offline English and Tamil engines, models, native decoder, and voice command routing",
    "smart command resolution, negation and parse-only Manager tester",
    "software discovery, user-authorized bulk refresh registration, duplicate refresh, dynamic Tanglish aliases, disable, missing-path restore and removal",
    "quit cleanup"
  ]
}
```

### Packaging the Windows Release & Installer
The automated packaging pipeline runs pytest, compiles the application via PyInstaller, and bundles it into a standalone Windows installer:

```powershell
.\release\build.ps1
```

This generates:
- `dist/v2/pet-animal/pet-animal.exe` (Packaged standalone desktop application)
- `dist/v2/Pet-Animal-2.0-Setup.exe` (Single-file Windows installer)

**Installer Features**:
- Installs to `%LOCALAPPDATA%\Programs\Pet Animal` without administrator privileges.
- Creates Start Menu shortcuts.
- Registers an uninstaller in Windows Settings ("Installed apps").
- Safely preserves your database, memories, and custom sprite sheets in `%LOCALAPPDATA%\PetAnimal` upon uninstallation.

### Release Artifact Verification
Verify frozen build integrity and installer payload:

```powershell
# 1. Verify frozen standalone executable self-test
Start-Process -Wait -WindowStyle Hidden -FilePath .\dist\v2\pet-animal\pet-animal.exe -ArgumentList '--self-test', 'K:\pet_animal\build\packaged-verification.json'

# 2. Verify installer package CRC and embedded payload
Start-Process -Wait -WindowStyle Hidden -FilePath .\dist\v2\Pet-Animal-2.0-Setup.exe -ArgumentList '--verify-payload', 'K:\pet_animal\build\installer-verification.json'
```

---

## License

Pet Animal 2.0 is licensed under the MIT License. See [LICENSE](LICENSE) for details. Multilingual Whisper components are licensed under the Apache 2.0 License (see [assets/speech/WHISPER-LICENSE.txt](assets/speech/WHISPER-LICENSE.txt)).
