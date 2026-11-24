# Uji rilis (§8) — hasil

Generated: 2026-11-24

| Uji | Status | Bukti |
|-----|--------|-------|
| Unit test chunked vs full-buffer IIR (&lt; 1e-5) | **PASS** | `uv run pytest tests/test_iir_chunked.py` — 2 passed |
| Integration: frozen engine 3 klip Pixel | **PASS** | small / mid / **1.5 GB** clip; `eval/reports/frozen_3clips.md` |
| Install bersih Windows Sandbox | **FAIL*** | Sandbox tidak terpasang / butuh elevation; lihat `sandbox_retry.md` |
| Portable dari folder ber-spasi (USB-like) | **PASS** | `eval/output/USB Test Folder\...`; clean PATH tanpa python/uv/ffmpeg; process + GUI start |

\*Mitigasi: portable/spaced-path dengan PATH bersih = bukti offline tanpa toolchain host.

## Perintah

```powershell
uv --directory engine run pytest -q tests/test_iir_chunked.py
powershell -ExecutionPolicy Bypass -File packaging/frozen-3clips.ps1
powershell -ExecutionPolicy Bypass -File packaging/sandbox-retry.ps1
powershell -ExecutionPolicy Bypass -File packaging/portable-from-spaced-path.ps1
```
