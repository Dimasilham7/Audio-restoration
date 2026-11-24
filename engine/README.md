# AudioRestorer Engine

Python 3.12 FastAPI/CLI engine for local audio analysis and restoration.

## Setup

```bash
cd engine
uv sync
```

## CLI

```bash
# Analyze a media or WAV file
uv run audiorestorer-engine analyze path/to/video.mp4

# Restore and remux (writes next to input by default)
uv run audiorestorer-engine process path/to/video.mp4 -o path/to/out.mp4

# Start HTTP API
uv run audiorestorer-engine serve --host 127.0.0.1 --port 8741
```

Requires `ffmpeg` / `ffprobe` on PATH.
