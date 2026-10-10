# Interactive pet memory lookup verification

Verified on Windows on 7 October 2026 using isolated temporary databases and sample credentials.

- Full project test run: **1,176 passed**.
- Final interactive-memory regression module: **55 passed**.
- Headless source self-test: **success** ([report](interactive-memory-source-verification.json)).
- Final whitespace check: **passed**.

The feature module verifies phrase variants, exact names and aliases, duplicate-name choices, partial password masks, password-name listings without decryption, card selection and individual field copies, actual Qt clipboard content, DPAPI errors, scope/disabled/expiry checks, edited/deleted records, session and field authorization, close/Escape/timeout behavior, long names, scrolling and screen positioning. Existing core, memory, application-shortcut and file-balloon regressions were checked after the final lifecycle refinements.

## Sample previews

- [Named password](screenshots/memory-password-balloon.png)
- [Password list](screenshots/memory-password-list-balloon.png)
- [Card list](screenshots/memory-card-list-balloon.png)
- [Card fields](screenshots/memory-card-fields-balloon.png)

All previews contain fabricated sample data. Existing encrypted memories use the same storage format. This verification covers the updated source; release executables were not rebuilt.

Run the source with the project virtual environment: `.venv\Scripts\python.exe src/main.py`.
