# Google Stitch Manager migration

The Manager uses Python and native PyQt6 widgets with Qt stylesheets. The existing headless core, SQLite schema version 7, application controller, command handlers and service interfaces remain the integration boundary. This migration changes the Manager presentation and packaging of its local UI resources. Pre-existing uncommitted work in the controller, core, interpreter and floating response widgets is retained.

## Stitch export and asset selection

`stitch_manager_app_design_system` contains six `code.html` layouts, six `screen.png` references and two design specifications (14 files). Dashboard, Memory, Commands, Workflows, Pet Studio and Settings are covered. Activity adopts the shared styles. `fluent_companion/DESIGN.md` supplies the blue palette, typography, spacing and component specifications; the unrelated coral `my_design_system/DESIGN.md` is excluded.

HTML is reference material: its Tailwind CDN, simulated interactions, sample records and remote mascot images are not part of the runtime. The application renders native Qt controls and uses its own Husky sprites.

The required local resources are:

- `assets/fonts/InterVariable.ttf`: upright Inter loaded through `QFontDatabase`, with Segoe UI fallback. `assets/fonts/OFL.txt` includes the SIL Open Font License. The source is the official Google Fonts Inter distribution; the [Inter project license](https://github.com/rsms/inter/blob/master/LICENSE.txt) describes the same licensing.
- `assets/ui/stitch/`: 30 Material Symbols SVGs with the upstream Apache license. Icons are tinted and rendered at logical bounds for high DPI. Missing icons fall back to an empty native icon without blocking actions.
- `assets/ui/stitch/sources.json`: upstream URLs and SHA-256 provenance for every copied font, icon and license.
- Existing `petimage` sprites are reused. No runtime network request is introduced for fonts, icons or Manager rendering.

`pet-animal.spec` now includes `assets/fonts`. Its existing recursive UI-assets inclusion bundles the SVGs, license and provenance manifest.

## Native component and file mapping

| File | Responsibility |
| --- | --- |
| `src/app/manager_window.py` | Existing public Manager entrypoints, navigation contract, tables, memory/command dialogs and handlers; lifecycle and theme refresh |
| `src/app/manager_ui/theme.py` | Light/dark design tokens, shared scoped Qt styles, local font registration |
| `src/app/manager_ui/icons.py` | Material SVG loading, aliases, theme tinting and high-DPI rendering |
| `src/app/manager_ui/widgets.py` | Cards, headings, badges, action buttons, wrapping action bars, responsive rows, checkbox switches and dropdowns |
| `src/app/manager_ui/pages.py` | Six page layout builders connected to the existing Manager methods and services |
| `src/app/manager_ui/workflow_view.py` | Persistent workflow panel composition: library, metadata, flow and step inspector |
| `src/app/manager_ui/preview.py` | Local Studio sprite preview with an owned timer, stopped on navigation and Manager hiding |
| `src/app/workflow_panel.py` | Existing drafts, selection, validation, save/run/stop, step edits and asynchronous execution feedback |
| `src/app/software_discovery.py` | Existing discovery state/worker and registration behavior with updated review presentation |
| `tests/test_stitch_manager_ui.py` | Focused navigation, command-filter/action identity, masking, signal lifecycle, preview, keyboard and layout regressions |
| `release/verify_stitch_ui.py` | Isolated seeded visual verification, screenshots, local-font and horizontal-overflow checks |
| `release/verify_stitch_package.py` | Bundled font/icon loading and copied-resource hash verification, alongside the frozen executable self-test |

Native tables, editors, file pickers, validation dialogs, the persistent `WorkflowPanel` and `SoftwareDiscoveryState` are reused. Navigation styling is scoped independently from workflow lists. Superseded inline Manager styles and workflow composition helpers have been removed.

## Completed vertical slices

1. **Foundation and shell:** native Windows title bar, 210 px sidebar, 24 px side margins, a 32 px top inset, 16 px gutters, rounded cards, light/dark palettes and local resources.
2. **Dashboard:** three live counters, active companion, recent activity and memory breakdown; real add/edit/navigation/show/hide actions. “View all activity” now navigates to Activity.
3. **Memory:** filtering, health badges, table and responsive detail inspector; existing specialized editors and maintenance actions. Refresh preserves record identity and resets sensitive reveal. Sensitive listings remain masked.
4. **Commands and discovery:** search/type/status filters, enabled switches, per-record actions and selected-record toolbar. Workflow editing is enabled for routine records. The interpretation tester remains parse-only; the discovery worker, valid-application registration and cancellation lifecycle are retained.
5. **Workflows:** persistent library, metadata/flow and inspector columns, compact stacking, existing six step types, reorder controls, actual status feedback and the real 50-step limit. Drafts, unsaved-change prompts, templates, duplication and stop behavior retain their original handlers.
6. **Studio, Settings and Activity:** local preview, identity/geometry/behavior cards; existing profile activation, slider ranges and coordinate handling; existing speech/hotkey/search/preferences/data save boundaries. Google speech's internet/audio-transfer notice remains conditional and visible when selected. Activity retains filters, routine details and clear confirmation.
7. **Cleanup and packaging:** local resources are bundled; page subscriptions disconnect on refresh and obsolete previews stop. No schema migration or core command API change is required.

Unsupported mockup features (chimes, docking, workflow CLI arguments, isolated step testing and re-indexing) are omitted. The floating pet presentation remains unchanged.

## Preserved behavior

The existing handlers continue to enforce memory CRUD/conflicts/expiry, explicit DPAPI reveal, safe JSON exports and encrypted backups; command phrase/reserved-pattern validation and execution; workflow draft persistence, validation, ordering and private history; software registration, speech engine/language/hotkey configuration and local file-search preferences; validated database/configuration imports and restore; independent window closing, tray access and shutdown cleanup.

## Verification

The complete regression suite passes **1,226 tests** (1,179 baseline tests plus 47 focused migration checks, including 12 header-alignment cases). The existing SpeechRecognition `aifc` deprecation warning remains.

The final source self-test, frozen executable self-test, installer archive/extracted application self-test and bundled-resource/source-parity checks all pass. The installer includes the same application executable and all 33 verified UI resources.

The machine-readable results are recorded in `docs/stitch-ui-verification.json`. Source self-test output is `build/stitch-source-verification.json`; the latest full-suite JUnit results are in `build/stitch-test-results.xml`.

The visual matrix contains 126 captures: seven pages × two themes × three logical sizes (1200×900, 1600×1000, 850×650) × three Qt scale factors (1, 1.25, 1.5). All fit the requested window size with zero content horizontal overflow and successfully load local Inter. Captures and per-scale reports are under `build/stitch-ui/`; representative images are copied to `docs/screenshots/stitch-*`.

These captures use Qt's offscreen platform and isolated fixture data. They verify layout and resource behavior at the requested scale factors, while native Windows title-bar interactions and OS display-setting transitions require an interactive Windows review. Automated launcher/recognition tests use mocks where opening external applications or transferring audio would otherwise occur. The source self-test also performs actual local software discovery without launching detected applications.

To repeat verification:

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=build/stitch-test-results.xml
.venv\Scripts\python.exe src/main.py --self-test build/stitch-source-verification.json
.venv\Scripts\python.exe release/verify_stitch_ui.py --scale 1 --output build/stitch-ui/1
.venv\Scripts\python.exe release/verify_stitch_ui.py --scale 1.25 --output build/stitch-ui/1.25
.venv\Scripts\python.exe release/verify_stitch_ui.py --scale 1.5 --output build/stitch-ui/1.5
.\release\build.ps1 -SkipTests
```

Use `-SkipTests` for packaging only after a successful full test run. Verify the resulting application with `--self-test` and the installer with `--verify-payload`; those reports and packaged resource hashes are included in the migration verification summary.

The resource check can be repeated with:

```powershell
.venv\Scripts\python.exe release/verify_stitch_package.py
```

It checks the packaged files using the local Qt runtime, including all 30 SVGs at three scale factors, and compares all ten packaged presentation modules with their source bytecode. The separate frozen executable self-test verifies that the packaged application imports and exercises its actual bundled Qt modules and Manager pages.

## Manager headroom adjustment

The Manager sidebar and page content now start 32 px from the top, up from 24 px. This adds a little space above the brand and all seven page headings while keeping their alignment. The focused Manager regression suite passes 35 checks; the 126 light/dark layout captures were refreshed at 100%, 125% and 150% Qt scale with no horizontal overflow.

## Header action alignment

The top action buttons on Dashboard, Memory, Commands, Pet Studio, and Activity now align with the right content edge. Workflow Save, Run, and Stop align with the right edge inside their header card. The shared action layout retains its button order and compact wrapping. A focused geometry check covers these six pages at 1600×1000 and 850×650.
