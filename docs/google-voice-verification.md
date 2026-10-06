# Google voice recognition verification

Verified on Windows 11, Python 3.14.3, 5 October 2026.

- Full test suite: **1,026 passed**, one existing SpeechRecognition `standard-aifc` deprecation warning.
- Source self-test: passed; see `google-source-verification.json`.
- PyInstaller executable build: passed.
- Packaged self-test: passed with exit code 0; see `google-packaged-verification.json`.
- Packaged Windows FLAC encoder: present and successfully encodes PCM into FLAC.
- Google requests: mocked throughout automated checks; verified HTTPS endpoint, English/Tamil language selection, 10-second timeout, errors, cancellation, silence rejection, recording limits, hold-to-talk, engine snapshots, and no automatic retries or local-engine fallback uploads.
- Settings: verified Google defaults, preservation of saved local-engine choices, language persistence, compatibility with older imports/backups, and invalid-value rejection.
- Settings layout: rendered offscreen with Windows fonts and visually inspected; see `screenshots/google-voice-settings.png`.
- `git diff --check`: passed.

Executable: `dist/google-verification/pet-animal/pet-animal.exe` (keep its `_internal` directory alongside it).

SHA-256: `ec34753eeab9092a5e0ca5e1285681f90f97dc9683eb63c530a57e7cfe19a886`

## Manual microphone verification still required

Live English/Tamil accuracy and actual Google service reachability have not been tested. Automated validation uploads no audio. To check manually, choose Google in Settings, select English (India) or Tamil (India), save preferences, and record a non-sensitive command using the microphone button and Ctrl + Windows shortcut. Check the failure message with internet disconnected. Whisper remains the local option for mixed Tamil/English utterances; Vosk remains the local streaming English option.

Google is the default for new configurations. Existing explicit English/Whisper settings are preserved. Google sends recorded audio to its service, uses SpeechRecognition's shared personal/testing key, and may become unavailable if that key is revoked. Cancellation suppresses results but cannot recall an already submitted request.
