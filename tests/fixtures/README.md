# Speech verification fixtures

`play-shape-of-you.wav` and `play-pause-shape-of-you.wav` were synthesized locally with Windows SAPI. The second fixture contains a one-second pause inside the command.

`tamil-fleurs.wav` is Google FLEURS Tamil (`ta_in`) test recording `10015420708072669120.wav`, row ID 1792, from the [Google FLEURS dataset](https://huggingface.co/datasets/google/fleurs). It is licensed under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Attribution: Google FLEURS authors and volunteer speaker. The original float WAV was converted to mono PCM16 at 16 kHz for local regression testing; speech was not edited. Original source: https://huggingface.co/datasets/google/fleurs/resolve/refs%2Fpr%2F29/data/ta_in/audio/test.tar.gz

This fixture verifies Tamil script recognition without translation. It does not measure command accuracy for a particular speaker or mixed-language accent.
