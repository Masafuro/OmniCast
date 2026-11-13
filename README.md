# OmniCast

Generate podcasts and multi-purpose narration audio from scripts using [k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice).

OmniCast provides a lightweight **FastAPI + Web UI** studio where you can import a `@Name: text` script, generate lines incrementally, retake individual lines and compare takes, tune pauses between utterances, preview playback continuously in the browser, and export a stitched `.wav` or `.mp3` episode via `ffmpeg`.

## Features (rev1)

- **Script Import / Export (`@Name: text`)**: Simple line-oriented script syntax with multi-line utterances and `#` comments.
- **5 Built-in Default Characters**: `Alice`, `Bob`, `Carol`, `Dave`, `Narrator` (mapped to OmniVoice Voice Design presets).
- **Per-Block Take Management**:
  - Generate / regenerate all unlocked lines at once (`一括 Generate`)
  - Retake individual lines (`🔄 リテイク`) and switch between generated takes (`T1`, `T2`, ...)
  - Lock finished lines (`🔒 ロック`) to protect them from accidental regeneration
  - Override reading (`tts_text`), speed, language, and style per line
- **Instant Pause Tuning & Continuous Playback**: Adjust `pause_after` per line in the GUI and preview continuously via Web Audio API.
- **Audio Export**: Stitch selected takes with silence trimming, fade-in, pause gaps, and optional loudness normalization (`ffmpeg`) to WAV or MP3.

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe`
- A running `k2-fsa/OmniVoice` Gradio Web UI (either on localhost or a separate GPU host on your network), or use `--mock` for offline UI testing.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` to point `OMNIVOICE_URL` at your OmniVoice Gradio server (for example `http://127.0.0.1:8000` when running on the same GPU machine).

## Run

```bash
omnicast
# Or run without a GPU/OmniVoice server using synthetic audio:
omnicast --mock
```

Then open `http://localhost:8080` (or `http://<server-ip>:8080` from another device on your LAN).

## Script Syntax

```text
# Comment lines are ignored
@Alice: こんにちは、OmniCast へようこそ！
@Bob: よろしくお願いします。
複数行にわたるセリフもそのまま書けます。
```

## Tests

```bash
pytest
```
