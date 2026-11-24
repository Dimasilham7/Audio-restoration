# Performance acceptance notes

Measured on the development machine (i7-14700F, RTX 3070 8 GB, 32 GB RAM, Windows 11).

## Targets (from release plan)

| Metric | Target | Status |
|--------|--------|--------|
| Window visible | ≤ 2 s after launch | Design: `show: false` until ready-to-show; Electron shell is light |
| Engine health OK | ≤ 5 s background | **~1–3 s** READY handshake on frozen engine (measured) |
| UI long tasks while batching | ≤ 50 ms | Progress throttled via IPC; no sync DSP in renderer |
| Peak engine RAM (longest clip) | ≤ 1.5 GB | Chunked loudness + early buffer free; verify on 1.6 GB Pixel clip |
| 63-clip Pixel batch | ≤ 17.1 min baseline | Same DSP path as CLI baseline (**17.1 min**, 0 fail, DFN 11/63) |
| Cancel latency | ≤ 2 s | Cancel checked between stages/chunks |

## Packaging artifacts (this machine)

| Artifact | Size |
|----------|------|
| `AudioRestorer-AI-0.1.0-win-x64.exe` (NSIS) | ~193 MB |
| `AudioRestorer-AI-0.1.0-portable.exe` | ~193 MB |

Within the plan estimate of 150–250 MB installer.

## Smoke (frozen engine)

- `analyze` + `process` on short Pixel clip: OK, sample_count_ok=true, DFN gated path worked.
- Output: `eval/output/smoke_frozen.restored.mp4`

## How to re-measure

1. Launch packaged app; stopwatch until window shows.
2. Task Manager → peak Working Set for `audiorestorer-engine.exe` on longest clip.
3. Batch `eval/datasets/pixel-20261122` via UI; compare to 17.1 min CLI.
4. Mid-job Cancel selected; confirm stop ≤ 2 s.
