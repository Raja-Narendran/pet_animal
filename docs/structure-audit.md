# Structure and cleanup audit

Audited on 2026-10-01 against the local checkout. Git was clean before cleanup.

## File tree

Package directories retain their `__init__.py` files and intentional public exports.
Generated caches, model contents, screenshots, and environment internals are summarized.

```text
K:/pet_animal/
|-- src/
|   |-- main.py                         GUI entry point and isolated self-test
|   |-- app/
|   |   |-- controller.py               Window lifecycle, core listeners, BrowserWorker
|   |   |-- manager_window.py           Six Manager pages and local widget builders
|   |   `-- pet_window.py               Floating window; standalone compatibility path
|   |-- components/
|   |   |-- pet.py                      Sprite animation and dragging
|   |   |-- command_box.py              Typed/voice input and input-state transitions
|   |   |-- response.py                 Response bubble and expiry
|   |   |-- voice_button.py             Microphone control
|   |   `-- audio_waveform.py           Live speech level display
|   |-- commands/
|   |   |-- model.py                    Command, CommandResult, ActionType
|   |   |-- parser.py                   Standalone rule-based parser
|   |   |-- executor.py                 Standalone command executor
|   |   |-- registry.py                 Action handler registry
|   |   |-- voice_phrases.py            Tamil/English voice phrase routing
|   |   `-- actions/                    base, help, open_application, open_url,
|   |                                  search_web, play_music
|   |-- config/settings.py             Paths, defaults, launcher and voice settings
|   |-- core/
|   |   |-- application.py              SQLite, memory, commands, profiles, backups
|   |   `-- secrets.py                  Windows DPAPI
|   |-- database/migrations/
|   |   `-- 001_initial.sql             Runtime schema resource
|   |-- services/
|   |   |-- windows_launcher.py         Allowlisted OS dispatch
|   |   |-- voice_input.py              Local engines, microphone, VoiceInputWorker
|   |   |-- youtube_automation.py       Playback resolution and optional Selenium mode
|   |   `-- youtube_worker.py           Standalone PetWindow background playback
|   `-- utils/
|       |-- logger.py                  Logging setup and logger access
|       `-- sprite.py                  Sprite slicing, scaling and cache
|-- release/
|   |-- build.ps1                      Model preparation, tests, app and installer build
|   |-- installer.py                   Installation and payload-verification entry point
|   |-- prepare_voice_model.py         Vosk preparation and endpoint configuration
|   |-- prepare_multilingual_voice.py  Whisper preparation and checksum validation
|   |-- runtime_diagnostics.py         Intended frozen-runtime diagnostic hook
|   `-- hooks/hook-webrtcvad.py         Intended PyInstaller hook for maintained wheels
|-- assets/
|   |-- ui/                            arrow-right.svg, brain.svg, brain-white.svg, zap.svg
|   `-- speech/                        License and locally prepared models (models ignored)
|-- petimage/                          Seven built-in Husky animation sheets
|-- tests/                             14 regression test modules, package marker
|   `-- fixtures/                      Three WAV samples and provenance README
|-- docs/                              Verification reports, screenshots, this audit
|-- requirements.txt                   Direct and transitive dependency pins
|-- pet-animal.spec                    Tracked PyInstaller application specification
|-- README.md                          Usage, development and release documentation
|-- .gitignore                         Environment, generated files and model exclusions
|-- .agents/, AGENTS.md, AGENT.md,
|   SKILL.md                           Local agent/runbook material; preserved
`-- .venv/, build/, .pytest_cache/      Local environment and generated artifacts; preserved
```

## Entry points and reachability

| Entry point | Route and purpose |
| --- | --- |
| `python src/main.py` | `main()` creates QApplication, ApplicationCore and ApplicationController; controller owns ManagerWindow and PetWindow. |
| `python src/main.py --self-test <report>` | `run_self_test()` exercises an isolated database, window lifecycle and offline speech engines. |
| `python -m pytest -q` | Collects all 14 test modules; Qt, legacy parser/executor, core, launcher, installer, voice and playback paths are covered. |
| `release/build.ps1` | Runs both model preparation scripts, pytest, PyInstaller using pet-animal.spec, archive creation and installer packaging. |
| `python release/prepare_voice_model.py` | Calls `prepare()` to validate/extract the Vosk model and configure trailing silence. |
| `python release/prepare_multilingual_voice.py` | Calls `prepare()` to obtain checksum-validated multilingual model files. |
| `python release/installer.py` | `main()` supports installer UI, payload verification and uninstall behavior. |
| `PetWindow(parser=..., executor=...)` | Compatibility construction used by component tests; uses the command registry and lazily imports YouTubePlayWorker for playback. |

Manager page renderers are reached through dynamic navigation dispatch. Qt event
handlers and signal callbacks must not be classified as dead merely because they
have no ordinary call site. `__init__.py` imports are public package exports.

## Cleanup applied

- Removed 21 unused imported names across six application modules and seven test
  modules. AST name-use inspection was followed by reference review; exports stayed.
- Consolidated identical typed-command, voice-command and browser-completion result
  display into `ApplicationController._show_result()`. Bubble text, animation duration,
  pet anchoring and failed-voice input retention keep their existing behavior.
- Removed 12 unreferenced SVGs: arrow-memory, brain-quick, chevron-right, clock,
  command-activity, command-quick, command, database, plus, shield-check,
  shield-memory and sparkles. Checked literal and dynamically constructed icon paths.
  `brain-white.svg` stays because primary buttons select it dynamically.
  The installer test's plus.svg is generated inside a fixture ZIP; it does not read
  the removed repository icon.
- Removed `all_files.txt`, a stale duplicate dump of source files with no consumers.

No Python modules, migrations, sprites, speech fixtures/models, licenses, agent
instructions or historical verification artifacts were deleted.

## Dependency audit

No listed dependency was proven unnecessary. No packages were uninstalled and the
manifest was preserved. Several entries are indirect requirements, not dead packages:

| Dependency group | Consumer |
| --- | --- |
| Pillow, PyQt6 | Core PNG validation and native UI/sprite rendering. |
| PyQt6-Qt6, PyQt6_sip | Required by PyQt6. |
| SpeechRecognition, vosk, sounddevice, faster-whisper, webrtcvad-wheels | Active microphone input, English and multilingual recognition, endpoint detection. |
| selenium | Optional YouTube service mode with explicit regression coverage. |
| pytest, pytest-qt | Test collection and Qt fixtures. |
| colorama, iniconfig, packaging, pluggy, Pygments | pytest dependencies; packaging is also required by PyInstaller. |
| pyinstaller | Release builder. |
| altgraph, pefile, pyinstaller-hooks-contrib, pywin32-ctypes, setuptools | PyInstaller dependencies on Windows. |

Dependency ownership was checked against installed distribution metadata.
`pip check` reports no broken requirements. A fresh dependency installation or
complete reproducibility audit was not performed.

## Structural findings and preserved boundaries

1. The guide/runbook describes voice and browser automation as disabled and 175
   tests. The checkout has active voice/playback paths and 232 tests. These features
   were preserved; removing them as legacy code would break existing behavior.
2. The core/controller/Manager separation remains intact. Core source does not import
   Qt. The standalone parser/executor and PetWindow callbacks overlap the controller
   flow but are live compatibility APIs, not orphan components.
3. Logger access/setup and the two model-preparation helpers serve distinct roles;
   merging them solely because they look similar would change contracts.
4. `Command.to_dict/from_dict` and `PetWindow.hide_to_tray` have no in-repository
   callers, but remain public compatibility methods. Absence of callers is not enough
   evidence to remove these methods safely.
5. The current `pet-animal.spec` includes only petimage in `datas`; migrations, UI
   icons and speech models are absent. `hookspath` and `runtime_hooks` are empty,
   leaving the webrtcvad and diagnostic hooks unwired. These files are necessary
   release support, not deletion candidates. This is a pre-existing packaging gap;
   repair and a fresh Windows build require separate validation. README release
   claims should not be treated as proof of the current spec's completeness.
6. Historical packaged reports and hashes describe earlier binaries. This cleanup
   did not rebuild or revalidate the installer, so those reports were preserved as
   historical evidence and were not overwritten.

## Verification

- Full suite before cleanup: 232 passed, one existing SpeechRecognition/aifc warning.
- Full suite after cleanup: 232 passed, the same warning.
- Application self-test: success; report at `build/cleanup-source-verification.json`.
  Verifies migrations, memory/backup restore, six Manager pages, profile changes,
  window independence, offline speech engines/models/routing and quit cleanup.
- AST recheck: no remaining unused-import candidates outside intentional package exports.
- `git diff --check`: passed.
- `pip check`: no broken requirements.

The checks cover source behavior and installed dependency consistency. Frozen app
and installer packaging were not rebuilt during this cleanup.
