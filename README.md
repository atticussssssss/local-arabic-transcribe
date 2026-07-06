# Arabic Subtitle SOP (local, offline, free)

A small, reproducible **standard operating procedure (SOP) / pipeline** for extracting
Arabic subtitles from video/audio on your own machine — no cloud, no API keys, no fees.
Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper large-v3).

It wraps the raw model with the pre/post-processing that makes commercial transcription
services noticeably better than a bare Whisper run:

- Audio normalization (16 kHz mono)
- Word-level timestamps → millisecond-accurate SRT
- Anti-hallucination decoding (no context carry-over, temperature fallback,
  compression-ratio / log-prob / no-speech thresholds, VAD)
- **Post-processing warnings**: suspicious segments (boilerplate hallucinations like
  "subscribe to the channel", over-long segments, repetitions) are *flagged for review,
  never silently deleted*.

> Focused on Arabic (esp. Gulf/Saudi colloquial), but works for any language via `WHISPER_LANG`.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# 1. Drop video/audio files into inbox/
# 2. Run:
python3 run.py
# ...or a single file:
python3 run.py /path/to/video.mp4
# 3. Collect results from outputs/
```

Each input produces three files in `outputs/`:

| File | What |
|------|------|
| `<name>.srt` | subtitles, millisecond timestamps |
| `<name>.txt` | plain text |
| `<name>.warnings.txt` | **segments to review by hand** (hallucinations / long / repeated) |

### Reuse an already-downloaded model

```bash
export WHISPER_MODEL=/path/to/faster-whisper-large-v3   # local dir, skips the 3GB download
export WHISPER_LANG=ar                                   # default: ar
```

## Always do this after a run

Open `outputs/<name>.warnings.txt` and check the flagged timestamps against the video.
The pipeline will **not** guess for you on hard/unclear audio — it points you at the risky
spots so you can verify them.

## Known limitation & the "pro" upgrade

The biggest weakness is **video with heavy background music/SFX**: Whisper tends to
hallucinate over music (the classic "subscribe to the channel" filler). Commercial
services solve this with **vocal separation**. To match that locally, add a
[Demucs](https://github.com/adefossez/demucs) vocal-isolation stage before transcription
(free, open-source; costs ~1–2 GB of extra downloads). PRs welcome.

## Notes on dialect

Most Gulf/Saudi source audio is colloquial (عامية), not Modern Standard Arabic (فصحى).
For a faithful transcript, colloquial forms (e.g. `لازم`, `يروحون`, dropped `أن`) are
**correct** and should be kept — only fix true errors (misspellings, garbage tokens,
wrong names, dropped words).

## Contributing

This started as a personal SOP and is opened up so others can improve it. Ideas welcome:
Demucs stage, better VAD, diarization, hallucination-filter tuning, GPU config, other languages.

## License

See [LICENSE](LICENSE).
