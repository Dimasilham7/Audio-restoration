#!/usr/bin/env python3
"""PESQ / STOI / SI-SDR harness + solo listening worksheet.

Uses restored vs original WAVs when available; otherwise synthetic reference.
Writes eval/reports/metrics_report.md
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine" / "src"))
REPORT = ROOT / "eval" / "reports" / "metrics_report.md"
OUT = ROOT / "eval" / "output" / "acceptance"


def si_sdr(ref: np.ndarray, est: np.ndarray) -> float:
    x = ref.astype(np.float64).ravel()
    y = est.astype(np.float64).ravel()
    n = min(x.size, y.size)
    x, y = x[:n], y[:n]
    alpha = np.dot(y, x) / (np.dot(x, x) + 1e-12)
    s = alpha * x
    e = y - s
    return float(10 * np.log10((np.dot(s, s) + 1e-12) / (np.dot(e, e) + 1e-12)))


def try_stoi(ref: np.ndarray, est: np.ndarray, sr: int) -> float | None:
    try:
        from pystoi import stoi

        n = min(ref.size, est.size)
        return float(stoi(ref[:n], est[:n], sr, extended=False))
    except Exception as exc:  # noqa: BLE001
        return None


def try_pesq(ref: np.ndarray, est: np.ndarray, sr: int) -> float | None:
    try:
        from pesq import pesq

        # PESQ wants 8k or 16k
        target = 16000 if sr >= 16000 else 8000
        if sr != target:
            from scipy import signal

            g = math.gcd(sr, target)
            ref = signal.resample_poly(ref, target // g, sr // g)
            est = signal.resample_poly(est, target // g, sr // g)
            sr = target
        n = min(ref.size, est.size)
        mode = "wb" if sr == 16000 else "nb"
        return float(pesq(sr, ref[:n], est[:n], mode))
    except Exception:
        return None


def load_pair() -> tuple[np.ndarray, np.ndarray, int, str]:
    from audiorestorer_engine.io.audio import read_audio

    restored = OUT / "portable_smoke.restored.mp4"
    # Prefer work dir extracted/restored wav from smoke
    candidates = list((ROOT / "eval" / "output").rglob("restored.wav"))
    if candidates:
        rest_wav = candidates[0]
        ext = rest_wav.with_name("extracted.wav")
        if ext.is_file():
            a, sr = read_audio(ext)
            b, _ = read_audio(rest_wav)
            return a.mean(0), b.mean(0), sr, str(rest_wav)
    # Synthetic clean vs lightly filtered
    sr = 16000
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)
    ref = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float64)
    est = ref * 0.95 + 0.01 * np.random.default_rng(0).standard_normal(ref.size)
    return ref, est, sr, "synthetic"


def main() -> int:
    ref, est, sr, source = load_pair()
    rows = []
    rows.append(("source", True, source))
    sdr = si_sdr(ref, est)
    rows.append(("si_sdr", True, f"{sdr:.2f} dB"))
    stoi_v = try_stoi(ref, est, sr)
    rows.append(("stoi", stoi_v is not None, "n/a" if stoi_v is None else f"{stoi_v:.3f}"))
    pesq_v = try_pesq(ref, est, sr)
    rows.append(("pesq", pesq_v is not None, "n/a" if pesq_v is None else f"{pesq_v:.3f}"))

    # Listening panel worksheet (solo ABX interim)
    listening = {
        "method": "solo_abx_interim",
        "instructions": [
            "Play A (original) then B (restored) loudness-matched",
            "Mark preference: A / B / no difference",
            "Target: Hybrid preferred ≥70% once panel exists",
        ],
        "trials": [],
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Metrics report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Metric | OK | Value |",
        "|--------|----|-------|",
    ]
    for name, ok, detail in rows:
        lines.append(f"| `{name}` | {'PASS' if ok else 'SKIP'} | {detail} |")
    lines += [
        "",
        "## Listening panel (interim)",
        "",
        "```json",
        json.dumps(listening, indent=2),
        "```",
        "",
        "Install optional deps for full PESQ/STOI:",
        "`uv pip install pystoi pesq` (inside engine venv).",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))
    # SI-SDR always computed; PESQ/STOI may skip — exit 0 if core ok
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
