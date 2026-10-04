# Structure and cleanup audit

Audited on 2026-10-03 against the current local checkout. Git was clean before
cleanup. This report replaces the 2026-10-01 audit, whose module/test counts and
packaging findings no longer describe the current codebase.

## File tree

64 Python files under src, 28 test modules, six release Python files, and six SQL
migrations. Package markers and public exports are retained. Model directories,
generated artifacts, and historical verification records are summarized below.

```text
K:/pet_animal/
|-- src/
|   |-- main.py                         GUI startup and isolated --self-test
|   |-- app/
|   |   |-- controller.py               Windows, lifecycle, BrowserWorker, FileSearchWorker
|   |   |-- manager_window.py           Six pages, dialogs and widget builders
|   |   |-- pet_window.py               Floating pet and standalone compatibility route
|   |   `-- software_discovery.py       Discovery worker, shared state and Manager panel
|   |-- components/
|   |   |-- pet.py                      Sprite display and dragging
|   |   |-- command_box.py              Typed/voice input and waveform integration
|   |   |-- response.py                 Text bubbles and interactive file results
|   |   |-- voice_button.py             Microphone control
|   |   `-- audio_waveform.py           Speech level display
|   |-- commands/
|   |   |-- model.py, parser.py          Compatibility command model and parser
|   |   |-- executor.py, registry.py    Compatibility execution and handler dispatch
|   |   |-- voice_phrases.py            Tamil/English/Tanglish routing and negation
|   |   |-- actions/                    base, help, open_application, open_url,
|   |   |                              search_web, play_music
|   |   `-- interpreter/               base, models, normalizer, patterns, rule_based,
|   |                                  resolver, memory_rules, memory_resolver, file_rules
|   |-- config/settings.py             Paths, defaults, speech and resource configuration
|   |-- core/
|   |   |-- application.py             SQLite, commands, profiles, settings and backups
|   |   |-- secrets.py                  Windows DPAPI
|   |   |-- shortcuts.py                Application autocomplete models and matching
|   |   |-- file_search.py              Search sessions and result authorization
|   |   `-- memory/                    models, service, retrieval
|   |-- database/migrations/
|   |   |-- 001_initial.sql
|   |   |-- 002_registered_applications.sql
|   |   |-- 003_personal_memory_engine.sql
|   |   |-- 004_simplify_memory.sql
|   |   |-- 005_remove_activity_patterns.sql
|   |   `-- 006_file_open_history.sql
|   |-- services/
|   |   |-- windows_launcher.py         Built-in/approved application and URL dispatch
|   |   |-- voice_input.py              Local speech models, capture and Qt workers
|   |   |-- youtube_automation.py       Playback resolution and optional Selenium route
|   |   |-- youtube_worker.py           Standalone PetWindow playback worker
|   |   |-- file_search.py              Everything/local search backends and path checks
|   |   |-- recent_files.py             Windows recent-item shortcut resolution
|   |   `-- software_discovery/         models, validator, service, registry, start_menu
|   `-- utils/                         logger, sprite
|-- release/
|   |-- build.ps1                      Model prep, tests, PyInstaller and installer build
|   |-- installer.py                   Install/uninstall UI and payload verification
|   |-- prepare_voice_model.py         Vosk setup and endpoint configuration
|   |-- prepare_multilingual_voice.py  Multilingual model setup/checksums
|   |-- runtime_diagnostics.py         Frozen boot diagnostics
|   `-- hooks/hook-webrtcvad.py         PyInstaller speech-wheel hook
|-- assets/
|   |-- ui/                            arrow-right.svg, brain.svg, brain-white.svg, zap.svg
|   `-- speech/                        WHISPER-LICENSE.txt and prepared local models
|-- petimage/                          Seven built-in Husky animation sheets
|-- tests/                             28 regression modules and package marker
|   `-- fixtures/                      Three WAV samples and provenance README
|-- docs/                              This audit, feature/release reports, screenshots
|-- requirements.txt                   Runtime/test/build dependencies and their pins
|-- pet-animal.spec                    Application packaging specification
|-- README.md                          Usage and development documentation
|-- .gitignore                         Generated-file/model exclusions
|-- .agents/, AGENTS.md, AGENT.md,
|   SKILL.md                           Local agent/runbook material where present
`-- .venv/, build/, dist/,
    .pytest_cache/                     Environment and generated outputs where present
```

## Entry points and dependency routes

| Entry point | Route |
| --- | --- |
| `python src/main.py` | `main()` creates QApplication, ApplicationCore and ApplicationController; controller owns ManagerWindow and PetWindow. |
| `python src/main.py --self-test <report>` | `run_self_test()` uses an isolated database to check migrations, DPAPI, memory, restore, pages, speech engines, smart commands, discovery and shutdown. |
| `python -m pytest -q` | 28 test modules exercise core, memory, interpreters, compatibility commands, Qt components, discovery, shortcuts, file search, speech, playback and installer behavior. |
| `release/build.ps1` | Runs both model preparation scripts and tests, packages pet-animal.spec, creates the payload archive and builds release/installer.py. |
| `python release/prepare_voice_model.py` | Explicit build/setup-time Vosk model preparation. |
| `python release/prepare_multilingual_voice.py` | Explicit build/setup-time checksum-validated multilingual model preparation. |
| `python release/installer.py` | Installer `main()` also handles payload verification and uninstall. |
| `PetWindow(parser=..., executor=...)` | Compatibility/test construction uses parser/executor/registry/actions and lazily loads YouTubePlayWorker. |
| PyInstaller hooks | pet-animal.spec references release/hooks and release/runtime_diagnostics.py directly; import-graph reachability alone cannot identify these consumers. |

Primary runtime flow:

```text
main -> controller -> ManagerWindow / PetWindow -> components
                  -> BrowserWorker / FileSearchWorker
core -> interpreter -> memory rules / preference resolver / intent resolver
     -> memory service -> retrieval / DPAPI / SQLite
     -> shortcuts / file-search sessions -> file-search service -> recent files
     -> software-discovery models/validation -> WindowsLauncher
Manager -> discovery state/worker/panel -> discovery service -> providers
command box -> voice input -> local Vosk/Whisper + sounddevice + endpoint detector
WindowsLauncher -> approved argument-list launches / URLs / playback service
```

AST import traversal used src.main, all tests and release scripts as roots and
resolved relative imports, package exports and imports inside functions. Every
implementation module is reachable. The only unvisited source file was the empty
src/database/__init__.py marker; migrations are loaded as filesystem resources,
so this package and all six SQL files remain necessary. Static checks were
supplemented with searches for signal callbacks, navigation dispatch, resource
paths, documentation references and packaging hooks.

## Cleanup applied

- Removed 16 unused imported names from Manager, memory retrieval and five test
  modules. QInputDialog became unused after removing its dead callback.
- Removed ManagerWindow.memory_choice: the enum combo builder has no callers after
  memory UI simplification. No signal or dynamic navigation route references it.
- Removed ManagerWindow.new_category: no UI control, test, or documented route calls
  this orphan callback. ApplicationCore.add_category remains available and tested.
- Removed warmup_models_async: no runtime, test, export or documentation consumer.
  Active speech startup still loads its model before opening the microphone.
  Thread locks and the actual model loaders remain intact.
- Shared identical casefold/whitespace normalization with memory.service.normalize.
  application.normalize stays as a forwarding wrapper, preserving its public
  name and normalize(text=...) keyword signature.
- Reused memory_rules.RAW_PREFIXES as normalizer.PREFIXES rather than constructing
  the identical polite-request prefix tuple twice. Both existing names remain.

No complete files, assets, migrations, fixtures, models, licenses, package markers,
public memory APIs, or verification archives were deleted. No packages were
uninstalled. No user database was changed by cleanup; regression fixtures and the
self-test use isolated databases.

## Dependency audit

All listed packages have runtime, testing, packaging or transitive consumers.
Requirements therefore remain unchanged. Removing a package solely because its
name never appears in an import would break dependency pins or optional paths.
Installed distribution metadata was inspected to confirm ownership.

| Dependency group | Consumer |
| --- | --- |
| pillow, PyQt6 | Core PNG checks and GUI/sprite rendering. |
| PyQt6-Qt6, PyQt6_sip | Required by PyQt6. |
| SpeechRecognition, vosk, sounddevice, faster-whisper, webrtcvad-wheels | Active local capture/recognition/endpoint detection. |
| selenium | Optional playback service route and regression coverage. |
| pytest, pytest-qt | Test runner, Qt fixtures. |
| colorama, iniconfig, packaging, pluggy, Pygments | pytest dependencies; packaging is also used by PyInstaller. |
| pyinstaller | Release build command. |
| altgraph, pefile, pyinstaller-hooks-contrib, pywin32-ctypes, setuptools | PyInstaller requirements on Windows. |

numpy is also directly imported by speech code/tests and supplied transitively in
the installed environment; this audit does not establish fresh-install lockfile
completeness. pip check verifies installed requirement consistency, not a clean
installation. Build/model preparation scripts may download assets; no network
preparation was run for this audit.

## Structural findings and preserved boundaries

1. The local guide/runbook still describes disabled voice/browser automation and
   175 tests. The current source has active speech/playback paths and 866 tests.
   These features were preserved. This cleanup does not resolve the historical
   offline-policy/documentation mismatch or change runtime capabilities.
2. src/core has no direct Qt or UI imports. src/services/voice_input.py includes Qt
   workers, so the entire services directory should not be described as headless.
   Package exports matter when tracing transitive imports: commands/__init__.py
   exports the compatibility executor/registry, and app/__init__.py exports PetWindow.
3. src/core/file_search.py controls sessions, expiry and authorization;
   src/services/file_search.py implements search backends. They are distinct layers.
   BrowserWorker and YouTubePlayWorker likewise serve separate controller and
   compatibility routes. Similar names are not evidence of duplication.
4. All six Manager page_* methods are reached by getattr navigation. Qt paintEvent
   methods are framework callbacks. Public Command serialization, PetWindow tray
   helpers and memory service convenience APIs remain even where ordinary callers
   are absent. These are not safe deletion candidates.
5. Lazy reverse imports exist: the discovery panel imports Manager widget builders,
   memory.service imports its retriever, and WindowsLauncher.search_web imports
   ApplicationCore for shared validation. They are live; broad helper relocation
   would require a separate refactor and import-cycle validation.
6. application.py (1104 lines) and manager_window.py (1118 lines) concentrate many
   responsibilities. Memory, discovery and search already have extracted modules;
   further splitting is a maintainability opportunity, outside this deletion audit.
7. The previous packaging gap is fixed in the current pet-animal.spec: petimage,
   UI assets, speech assets and migrations are in datas; Vosk libraries are collected;
   release/hooks and runtime_diagnostics.py are wired. These release files remain.
8. All four SVG files have direct or dynamic button consumers; brain-white.svg is
   chosen for a primary button. All seven sprites and six migrations have runtime
   consumers. No additional orphan resource was proven safe to remove.
9. Historical packaged/installer reports describe prior binaries. They are retained
   as evidence; this cleanup does not rebuild or validate new frozen artifacts.

## Verification

- Initial full-suite run: 866 passed, one existing SpeechRecognition/aifc warning.
  Cleanup edits overlapped this run, so it is not a strict pre-change baseline.
- Final full-suite run: 866 passed in 86.57 seconds; one existing
  SpeechRecognition/aifc deprecation warning.
- Isolated source self-test: success; build/cleanup-source-verification.json.
- AST import/name-use recheck: no unexplained unused imports. Intentional package
  exports and the compatibility PREFIXES alias remain.
- Core boundary scan: no direct Qt/UI imports under src/core.
- git diff --check: passed.
- pip check: no broken requirements.

Source verification and static packaging review do not confirm a freshly built
installer or a clean dependency installation.
