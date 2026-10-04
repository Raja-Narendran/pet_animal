# Local file search verification

Verified on 3 October 2026 with Windows, Python 3.14.3 and the repository virtual environment.

- Full regression suite: **853 passed**, with the existing speech-recognition `aifc` deprecation warning.
- Focused file-search suite after final Everything scope quoting: **79 passed**.
- Existing offscreen application self-test: **success**, report at `build/source-file-search-verification.json`.
- Native Windows rendering inspected for Settings in light/dark themes and the example file-search response. Screenshots are in `build/file-search-settings-light.png`, `build/file-search-settings-dark.png` and `build/file-search-response.png`. Long paths wrap and their original text remains available in a tooltip.
- `git diff --check`: passed.

The new tests verify the requested three-file/multiple-result conversations, Salesforce detection and Yes confirmation, explicit folder queries and unique-folder opening, slash syntax, extension filtering, modification-time ordering, scope boundaries, pagination, expired/stale searches, cancellation, pending follow-ups, background Qt execution, settings backup/restore, history privacy and executable/script/shortcut rejection. Existing app, web, memory and shortcut regressions remain covered by the full suite.

Everything and `es.exe` were not installed on this verification host. The adapter was verified with controlled CSV/IPC responses, including Unicode/comma paths, scope filters, empty results, malformed output, timeout and IPC errors. A live Everything end-to-end query remains unverified. The local filesystem fallback was exercised with real temporary files and folders.

Integration uses the official [Everything ES CLI](https://www.voidtools.com/support/everything/command_line_interface/) over local IPC. Configure it in Settings → Local file search, alongside optional local search roots. No runtime downloads, external services or additional Python dependencies are introduced.

This verification covers the source changes. Existing release executables and installer packages have not been rebuilt. The pre-existing local changes to `src/main.py` were preserved.
