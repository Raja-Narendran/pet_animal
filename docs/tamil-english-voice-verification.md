# Tamil and English voice verification

Date: 1 October 2026. Windows 11, Python 3.14.3, CPU recognition.

## Behavior

Voice input uses the bundled multilingual Whisper small model (CPU int8, local files only). Microphone PCM stays in memory. WebRTC VAD waits for at least 1.5 seconds of final silence; a one-second pause stays inside the same utterance. The existing live waveform and cancel control remain active. A recording that reaches the 60-second safety limit is rejected rather than executed.

Explicit Tamil/Tanglish command templates route through existing allowlisted commands and browser actions. Both requested examples are covered: `Shape of You பாட்டு play பண்ணு` and `Chrome open பண்ணு`. Exact custom phrases and disabled commands take precedence. Tamil song/query text is preserved, and unsupported phrases remain redacted in history. Typed matching is unchanged.

## Validation

- Full automated suite: 226 tests passed before adding the public Tamil recording regression.
- Final multilingual module: 25 tests passed, including that additional native Tamil recording test.
- Source self-test passed, including local model initialization, a native CPU decode, silence detection, both mixed-language routes, isolated database restore, window lifecycle and cleanup.
- Native speech endpoint checks passed at 16 kHz and a 44.1 kHz microphone fallback rate.
- A real synthesized English command with an internal one-second pause still resolves to `play shape of you`, including recognition punctuation.
- Google FLEURS Tamil test recording 10015420708072669120.wav produced Tamil script without translation. Fixture provenance and CC-BY-4.0 attribution are in [the fixture readme](../tests/fixtures/README.md).
- Tamil text was visually inspected in the chat input using Windows font fallback.

## Limits

The public Tamil sample verifies offline Tamil transcription; it does not establish perfect word accuracy. The small model made some word errors in this sample. The user's own mixed-language speech/accent and physical microphone have not been exercised by these automated checks. CPU transcription can take several seconds; the recognition bar remains visible and cancellation suppresses late results. Tests use isolated data and mocked external launches.

Models are downloaded only by setup/build scripts and verified against pinned checksums. The runtime uses local files only. The release also retains the English Vosk developer fallback. The bundled Whisper weights retain their MIT license notice.

## Packaged application

`dist/tamil-english/pet-animal/pet-animal.exe` passed its isolated self-test. This includes loading the bundled multilingual model and consuming a native CPU transcription, so the frozen distribution verifies the decoder as well as Python imports. Reports: [source check](tamil-english-source-verification.json), [packaged check](tamil-english-packaged-verification.json). The WebRTC wheels metadata and native extension are included through a custom PyInstaller hook.

The installer `dist/tamil-english/Pet-Animal-2.0-Setup.exe` also passed payload CRC/extraction and the extracted executable's full self-test. See [installer verification](tamil-english-installer-verification.json) and [artifact hashes](tamil-english-artifact-hashes.json). This verification does not install the application or change user data.
