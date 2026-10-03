# Interactive file and folder results verification

Implemented in the source app: file/folder rows in the floating pet balloon, one-click opening, keyboard selection/opening/dismissal, five visible rows with scrolling, full-path tooltips, and Recently opened / Recently changed controls. Search folders now require selection rather than opening automatically.

Recent ordering combines bounded Windows Recent Items metadata with successful Pet opens. Windows timestamps are approximate and coverage is incomplete. Unrecorded results follow by modification time. Windows shortcut targets are read through native COM GetPath without executing or resolving shortcuts. Pet history is bounded to 2,000 paths and stored in migration version 6; Windows activity remains in memory. Existing safe-launcher restrictions remain enforced.

Validation:
- Full pytest suite: 866 passed, one existing speech-recognition deprecation warning.
- Focused interaction tests: history merge/scope/order, stale/expired selection, failed opens, real native shortcut reading, mouse click, keyboard opening/dismissal, scrolling, replacement, screen-edge positioning, balloon expiry, cancellation, malformed shortcuts, restart persistence, and version-5 backup migration.
- Headless self-test: success; report at build/interactive-file-results-verification.json (schema version 6).
- Native Windows balloon render visually inspected: build/interactive-file-balloon.png. Five readable rows, sorting controls, scrollbar, and distinct file icon verified. Offscreen font rendering was unsuitable for visual review; native Windows rendering was used.
- Git whitespace check passed.

No installer or packaged-release rebuild was performed. Everything end-to-end availability is unchanged from the existing search integration; this change adds history enrichment and interactive presentation over that backend and the local fallback.
