# Gap closure — implement & test

Generated: 2026-11-24

| Former gap | What we did | Test result |
|------------|-------------|-------------|
| 9 screens + uncertainty UX | Full nav for Welcome/Import/Analysis/Diagnosis/Restore/A-B/Export/Models/Settings; confidence + recoverability chips; music speech-block note | `pnpm typecheck` + `pnpm build` PASS |
| SQLite schema | `resources/migrations/001_init.sql` + `sql.js` WAL-like persist (better-sqlite3 blocked: no VS C++) | `node scripts/test-db.mjs` PASS (migration v1 + project insert) |
| PESQ/STOI + listening | `eval/scripts/run_metrics.py` + solo ABX worksheet | STOI PASS (1.000); SI-SDR PASS; **PESQ SKIP** (needs MSVC to build `pesq`) |
| Windows Sandbox | `packaging/sandbox-attempt.ps1` + WSB | Sandbox **not enabled / needs elevation**; portable smoke **PASS** as offline fallback |
| V2/V3 Demucs/AudioSR | Adapters scaffolded, opt-in env, disabled by default | `tests/test_v2_v3_adapters.py` PASS |
| Phase 0 research | `eval/scripts/phase0_research.py` | DFN CLI + nvidia-smi evidenced; ONNX/PANNs/Demucs/Torch still **OPEN** by design |

## Commands

```powershell
cd apps/desktop; node scripts/test-db.mjs; pnpm typecheck; pnpm build
cd ../..
uv --directory engine run pytest -q
uv --directory engine run python ..\eval\scripts\run_metrics.py
uv --directory engine run python ..\eval\scripts\phase0_research.py
powershell -ExecutionPolicy Bypass -File packaging\sandbox-attempt.ps1
powershell -ExecutionPolicy Bypass -File packaging\portable-smoke.ps1
```

## Still open (honest)

1. Enable Windows Sandbox as Administrator to run full clean-install checklist.  
2. Install VS Build Tools to compile `pesq` (or use a wheel).  
3. Torch CUDA / PANNs license / Demucs concert listening remain Phase 0 OPEN.  
4. V2/V3 models intentionally not downloaded/bundled (license).
