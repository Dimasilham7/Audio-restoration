# Metrics report

Generated: 2026-11-24 19:57:01

| Metric | OK | Value |
|--------|----|-------|
| `source` | PASS | D:\portofolio\audio-restoration\eval\output\acceptance\work_PXL_20261122_140117882\restored.wav |
| `si_sdr` | PASS | 17.68 dB |
| `stoi` | PASS | 1.000 |
| `pesq` | SKIP | n/a |

## Listening panel (interim)

```json
{
  "method": "solo_abx_interim",
  "instructions": [
    "Play A (original) then B (restored) loudness-matched",
    "Mark preference: A / B / no difference",
    "Target: Hybrid preferred \u226570% once panel exists"
  ],
  "trials": []
}
```

Install optional deps for full PESQ/STOI:
`uv pip install pystoi pesq` (inside engine venv).
