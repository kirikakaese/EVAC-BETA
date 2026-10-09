# ADR-0022: Offline speech for announcements with Piper

- Status: Accepted
- Date: 2026-10-09

## Context

Roadmap ticket 2.7 and brief §6: optional offline TTS (Piper, English voice) to generate audio for screens with
speakers and, later, DIAL phone broadcasts; pre-render and cache. Brief §16: speech runs locally and is an
optional download, not baked into the default image. `piper-tts` with `onnxruntime` is about 220 MB, a voice
60–120 MB.

## Decision

- **Optional install**: Piper is found as an executable (`EVAC_PIPER_BINARY`, default `piper` on the path); it
  comes from `pip install -e .[tts]` or the image build argument `WITH_TTS=1` (off by default). Voices are
  `<name>.onnx` + `.onnx.json` files in `EVAC_TTS_VOICES_DIR` (default `MEDIA_ROOT/tts/voices`), installed with
  `manage.py evac_tts install <url or file>` (tar packages and plain `.onnx` files); `evac_tts list/status/say`
  help to check the setup. The voice is chosen per event (*Settings → Announcements*; default: the first English
  one).
- **Per level**: levels get *read aloud on screens* (on for the built-in urgent and emergency levels).
- **Pre-render on approval**: when an announcement for screens on such a level is approved, an outbox job runs
  Piper (subprocess, 2-minute timeout, temporary directory) and, when ffmpeg is present, converts to
  loudness-normalised AAC (48 kHz mono, 64 kbit/s; WAV otherwise). Files are named by a hash of voice and text, so
  the same text is rendered once. The announcement records the state (being prepared, ready, failed, no voice) and
  the announcement page plays the result; publishers can prepare it again.
- **Screens**: the program carries a per-screen signed URL (`/player/api/announcements/speech/<hash>.m4a?s=…`) on
  overlays and full-screen entries. The player pre-fetches the files (its service worker caches them by hash) and
  speaks once per appearance after the level's sound, one announcement after the other, only where the screen's
  display settings allow sound. A file that arrives after the announcement appeared is still spoken.
- **Own spoken text**: the composer offers *Spoken text* (`channel_texts["speech"]`, up to 1000 characters);
  default "Level. Title. Text."

## Consequences

- No new required dependency; the default image stays the same size.
- An announcement sent the moment it is approved may show a few seconds before its speech is ready; the speech
  follows when it is.
- DIAL phone broadcasts (phase 4) can reuse the rendered files.
- CI uses a fake Piper; a real Piper and voice are checked with an opt-in test (`EVAC_TEST_PIPER`).
