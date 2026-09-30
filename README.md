# Pet Animal — Floating Desktop Companion (V1)

A lightweight, cute, frameless, and transparent floating pet companion for the Windows desktop. The companion stays above normal windows, can be dragged anywhere, and features a small interactive command box to execute predefined desktop tasks (such as launching applications or opening websites).

---

## Architecture Diagram

```text
                  🐕
             ┌──────────┐
             │   PET    │
             └────┬─────┘
                  │  (Click to toggle)
        ┌─────────▼─────────────────┐
        │ What should I do?       ➤ │
        └─────────┬─────────────────┘
                  │  "open chrome"
        ┌─────────▼─────────────────┐
        │       Command Parser      │  (RuleBasedCommandParser)
        └─────────┬─────────────────┘
                  │  Command(OPEN_APPLICATION, "chrome")
        ┌─────────▼─────────────────┐
        │      Command Executor     │  (CommandExecutor & Registry)
        └─────────┬─────────────────┘
                  │  Safe Whitelisted Dispatch
        ┌─────────▼─────────────────┐
        │      Windows Launcher     │  (WindowsLauncher)
        └─────────┬─────────────────┘
                  │
                  ▼
              🟢 Chrome
```

---

## Project Overview

`pet-animal` V1 is a deterministic desktop automation tool designed to feel like an adorable desktop companion. It uses native per-pixel alpha transparency and high-DPI pixel-perfect scaling to render 64×64 pixel art sprite sheets cleanly without blur or window borders.

In V1, **no AI/LLM models, external APIs, or heavy browser engines** are used. The architecture is modular and decoupled so that in future versions, an AI or Natural Language Parser can be dropped in without changing the UI, the command models, or the execution engine.

---

## Features (V1)

- **Frameless & Transparent Window**: Floating companion with no title bars, window chrome, or borders.
- **Always on Top**: Remains visible above standard desktop windows.
- **Draggable Companion**: Smooth dragging with mouse-drag detection that prevents accidental clicks.
- **Interactive Command Box**: Compact command box toggled by clicking the pet; supports Enter key and Send button (`➤`).
- **Pixel Art Sprite Sheets**: Loads and renders sprite animations from `petimage/` with states for `idle`, `working`, `thinking`, `success`, `error`, `greeting`, and `sleeping`.
- **Speech Bubble Response**: Contextual speech bubbles displaying execution feedback and help.
- **System Tray Integration**: Minimize to system tray or right-click to access context menu (Toggle Box, Help, Sleep, Reset Position, Exit).
- **Position Persistence**: Automatically saves and restores the last desktop location on next launch.
- **Deterministic & Secure**: Strict whitelist of safe commands; raw user input is never passed to a shell.

---

## Requirements

- **Operating System**: Windows 10 or Windows 11 (64-bit)
- **Python**: Python 3.10+ (Tested on Python 3.14)
- **Dependencies**: `PyQt6`, `Pillow`, `pytest` (listed in `requirements.txt`)

---

## Installation

1. Clone or navigate to the repository directory:
   ```powershell
   cd k:\pet_animal
   ```

2. Create a virtual environment:
   ```powershell
   python -m venv .venv
   ```

3. Activate the virtual environment:
   ```powershell
   .venv\Scripts\Activate.ps1
   ```

4. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

---

## Development

To launch the desktop companion in development mode:

```powershell
.venv\Scripts\python src\main.py
```

To run all unit tests:

```powershell
.venv\Scripts\pytest -v
```

---

## Build (Standalone Executable)

To build a standalone Windows `.exe` application bundle using PyInstaller:

```powershell
.venv\Scripts\pyinstaller --clean --noconfirm --onedir --windowed --name pet-animal --add-data "petimage;petimage" src/main.py
```

The resulting standalone executable is generated in:
```text
dist/pet-animal/pet-animal.exe
```

---

## Supported Commands

The parser normalizes input by trimming leading/trailing whitespace, collapsing internal spaces, and handling case-insensitivity. Supported commands can be prefixed with `open`, `launch`, `start`, `run`, or entered directly:

| Command | Aliases / Variations | Action Executed |
| :--- | :--- | :--- |
| **Open Chrome** | `open chrome`, `launch chrome`, `start chrome`, `open google chrome` | Launches Google Chrome |
| **Open Notepad** | `open notepad`, `launch notepad`, `start notepad` | Launches Windows Notepad (`notepad.exe`) |
| **Open Calculator** | `open calculator`, `launch calculator`, `start calculator`, `open calc` | Launches Windows Calculator (`calc.exe`) |
| **Open File Explorer** | `open explorer`, `open file explorer`, `launch explorer`, `start explorer` | Opens Windows File Explorer (`explorer.exe`) |
| **Open VS Code** | `open vscode`, `open vs code`, `launch vscode`, `start vscode` | Resolves and launches Visual Studio Code (`code.exe` / `code.cmd`) |
| **Open YouTube** | `open youtube`, `launch youtube`, `youtube` | Opens `https://www.youtube.com` in the system default browser |
| **Open Google** | `open google`, `launch google`, `google` | Opens `https://www.google.com` in the system default browser |
| **Help** | `help`, `commands`, `?`, `show help` | Displays list of supported commands in pet speech bubble |

---

## Architecture

The project adheres to strict separation of concerns:

```text
src/
├── app/
│   └── pet_window.py          # Main frameless, transparent, always-on-top window
├── components/
│   ├── pet.py                 # PetWidget with animation, drag tracking, and click signals
│   ├── command_box.py         # CommandBoxWidget with text input and submit trigger
│   └── response.py            # ResponseBubbleWidget with auto-dismissing speech bubble
├── commands/
│   ├── model.py               # Normalized Command & CommandResult models
│   ├── parser.py              # RuleBasedCommandParser (BaseCommandParser interface)
│   ├── registry.py            # CommandRegistry mapping ActionTypes to Handlers
│   ├── executor.py            # CommandExecutor safely orchestrating actions
│   └── actions/
│       ├── base.py            # BaseCommandHandler abstract base
│       ├── open_application.py# OpenApplicationHandler
│       ├── open_url.py        # OpenUrlHandler
│       └── help.py            # HelpHandler
├── services/
│   └── windows_launcher.py    # WindowsLauncher (safe process spawner, no shell=True with user text)
├── config/
│   └── settings.py            # Application dimensions, paths, and configuration
├── utils/
│   ├── logger.py              # Lightweight logging setup
│   └── sprite.py              # SpriteManager slicing 64x64 sprite sheet frames
└── main.py                    # Entry point initializing QApplication and PetWindow
```

### Future AI Layer Compatibility

The command engine is decoupled into two independent interfaces:

1. **Parser (`BaseCommandParser`)**:
   - `parse(text: str) -> Command`
   - In V1: `RuleBasedCommandParser` matches deterministic patterns and keywords.
   - In V4 (Future): An AI parser (e.g. LLM JSON-function calling) can implement `BaseCommandParser` and emit the exact same `Command(action, target)` structure without changing any downstream code.
2. **Executor (`CommandExecutor`)**:
   - Consumes only structured `Command` objects, agnostic of how the command was parsed (rule-based, AI, voice, or webhook).

---

## Security

This application enforces strict security principles:

1. **No Arbitrary Shell Execution**: User text is **never** passed into `subprocess.Popen(..., shell=True)` or `cmd.exe /c`.
2. **Strict Whitelist**: Only predefined application targets (`chrome`, `notepad`, `calculator`, `explorer`, `vscode`) and validated URLs (`https://`) can be launched.
3. **Graceful Failures**: If a user enters unrecognized or malicious commands (e.g. `rm -rf`, `delete everything`, `powershell ...`), the parser marks the command as `ActionType.UNKNOWN` and the pet responds politely without executing anything.

---

## Future Roadmap

The application architecture is prepared for future extension:

- **V2**: Natural-language AI command parser (local or cloud LLM replacing `RuleBasedCommandParser`).
- **V3**: Desktop automation, pet personality moods, context memory, and system notifications.
