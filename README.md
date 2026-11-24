# AudioRestorer AI

Local-first Windows desktop application for AI- and DSP-based audio restoration from video or audio files.

**Status:** Windows release packaging available (`pnpm release:win`).

## Windows release (.exe)

Build offline installer + portable exe (no Python/uv/FFmpeg required on target PCs):

```powershell
pnpm install
pnpm release:win
```

Artifacts land in `apps/desktop/release/`:

- `AudioRestorer-AI-*-Setup.exe` (NSIS installer)
- `AudioRestorer-AI-*-portable.exe`

### SmartScreen

Portfolio builds are **unsigned**. Windows may show “Windows protected your PC”. Choose **More info → Run anyway**. Code signing can be added later.

### Licenses

Installer ships FFmpeg (GPL essentials) and DeepFilterNet CLI (MIT/Apache). See `resources/licenses/THIRD_PARTY.txt` after `pnpm fetch:binaries`.

### Clean install test (Windows Sandbox)

1. Enable Windows Sandbox.
2. Copy the Setup.exe into the sandbox.
3. Install (no Python/ffmpeg on the clean image).
4. Add a folder of videos → Process all → A/B audio.
5. Open remuxed MP4 in the sandbox video player.

## Dev quick start

### Engine

```bash
cd engine
uv sync
# ffmpeg on PATH, or set AUDIORESTORER_BIN_DIR
uv run audiorestorer-engine analyze path/to/video.mp4
uv run audiorestorer-engine process path/to/video.mp4 -o path/to/out.mp4
uv run audiorestorer-engine serve --port 8741
```

### DeepFilterNet3

Place CLI at `.models/deepfilternet/deep-filter.exe` or `apps/desktop/resources/bin/deep-filter.exe`, or set `AUDIORESTORER_DFN_EXE`.

### Desktop (dev)

```bash
pnpm install
pnpm fetch:binaries   # optional; copies ffmpeg + deep-filter into resources/bin
pnpm dev
```

The desktop app starts a **persistent engine sidecar** (not `uv run` per click).

## Architecture (release)

- Electron UI → IPC → main process → HTTP sidecar `audiorestorer-engine.exe`
- Bundled `ffmpeg` / `ffprobe` / `deep-filter` under `resources/bin`
- Progress via job queue + SSE

## Documentation

See [`docs/`](docs/) for full planning docs. Perf checklist: [`packaging/PERF_NOTES.md`](packaging/PERF_NOTES.md).

## License

GPL-3.0-or-later. Third-party components retain their own licenses.
