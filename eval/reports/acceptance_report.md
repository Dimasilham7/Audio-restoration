# Acceptance report

Generated: 2026-11-24 (re-run after cancel fix)

**Summary: all automated checks in this run PASSED** (unit hard gates + 3 Pixel clips + HTTP API + security static + portable layout + portable engine smoke).

## Ran and passed

| Area | Result |
|------|--------|
| Hard gates 1,3,4,5*,6,8,9 + planner music safety (13) | PASS (`pytest` 13 tests) |
| Sample count / duration drift / LUFS±0.5 / true-peak / finite on 3 Pixel clips | PASS |
| Cancel ≤ 2 s (after DFN kill + progress cancel) | PASS (~0 s after flag) |
| Engine HTTP: health, auth 401, capabilities, jobs analyze complete | PASS |
| Electron security static (`sandbox`, no nodeIntegration, contextIsolation, media://) | PASS |
| Packaged `win-unpacked` layout (exe, engine, ffmpeg, dfn, licenses) | PASS |
| Portable bundled-engine smoke analyze+process | PASS |

\*Gate 5 SI-SDR measured vs **conditioned** reference (DC-block alone already moves SI-SDR vs raw).

## Still not tested / blocked

| Item from gap list | Why |
|--------------------|-----|
| Formal PESQ / STOI / DNSMOS + blind preference listening | No listening panel / metric harness yet |
| 9 screens + full uncertainty UX | UI is batch queue + A/B only; screens not built |
| SQLite schema / migrations | Not implemented in app |
| Full zod IPC contract suite | Partial (HTTP API exercised; renderer zod not wired end-to-end) |
| Windows Sandbox clean install | Feature needs elevation (`Containers-DisposableClientVM`); checklist exists in `packaging/SANDBOX_TEST.md` |
| 2-hour stereo OOM gate | Not executed (too long for this run) |
| V2/V3 Demucs / AudioSR | Deferred by design |
| Phase 0 unverified (DFN ONNX parity, Torch CUDA VRAM, PANNs license, EfficientAT, Demucs concert) | Still open research items |

## How to re-run

```powershell
uv --directory engine run python ..\eval\scripts\run_acceptance.py
powershell -ExecutionPolicy Bypass -File packaging\portable-smoke.ps1
```

Report path: `eval/reports/acceptance_report.md`
