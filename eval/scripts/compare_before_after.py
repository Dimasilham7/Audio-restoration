"""Compare original vs restored audio metrics for Pixel batch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from audiorestorer_engine.dsp.loudness import measure_loudness
from audiorestorer_engine.io.audio import read_audio
from audiorestorer_engine.io.ffmpeg import extract_audio

SRC = ROOT / "eval" / "datasets" / "pixel-20261122"
OUT = ROOT / "eval" / "output" / "all"
WORK = OUT / "compare_work"
REPORT = OUT / "before_after_comparison.json"

# Representative mix: DFN and DSP-only, short+long
SAMPLES = [
    "PXL_20261122_155218066.mp4",  # dfn
    "PXL_20261122_134530298.mp4",  # dfn
    "PXL_20261122_135147818.mp4",  # dfn
    "PXL_20261122_141633892.mp4",  # dsp
    "PXL_20261122_140545718.mp4",  # dsp
    "PXL_20261122_144108549.mp4",  # dsp
    "PXL_20261122_151445851.mp4",
    "PXL_20261122_134054089.mp4",
]


def metrics(audio: np.ndarray, sr: int) -> dict:
    mono = np.mean(audio, axis=0) if audio.shape[0] > 1 else audio[0]
    loud = measure_loudness(audio, sr)
    peak = float(np.max(np.abs(audio)) + 1e-12)
    rms = float(np.sqrt(np.mean(mono**2)) + 1e-12)
    crest = 20.0 * np.log10(peak / rms)
    clip = float(np.mean(np.abs(mono) >= 0.99))

    hop = 2048
    S = np.abs(librosa.stft(mono, n_fft=2048, hop_length=hop)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    mid = np.logical_and(freqs >= 500, freqs < 2000)
    high = freqs >= 4000
    mid_e = float(np.mean(S[mid]) + 1e-12)
    high_e = float(np.mean(S[high]) + 1e-12)
    hf_ratio = high_e / mid_e
    centroid = float(np.sum(freqs[:, None] * S) / (np.sum(S) + 1e-12))

    # Hiss proxy: energy in quietest 20% frames, high band
    frame_e = np.mean(S, axis=0)
    quiet = frame_e <= np.percentile(frame_e, 20)
    quiet_hf = float(np.mean(S[high][:, quiet]) + 1e-12) if np.any(quiet) else 0.0

    if audio.shape[0] > 1:
        corr = float(np.corrcoef(audio[0], audio[1])[0, 1])
        if not np.isfinite(corr):
            corr = 0.0
        l = float(np.sqrt(np.mean(audio[0] ** 2)) + 1e-12)
        r = float(np.sqrt(np.mean(audio[1] ** 2)) + 1e-12)
        balance = 20.0 * np.log10(l / r)
    else:
        corr, balance = 1.0, 0.0

    return {
        "lufs": round(loud["integrated_lufs"], 2),
        "true_peak_dbtp": round(loud["true_peak_dbtp"], 2),
        "crest_db": round(crest, 2),
        "clipping_ratio": round(clip, 5),
        "centroid_hz": round(centroid, 1),
        "hf_ratio": round(hf_ratio, 4),
        "quiet_hf_energy": round(quiet_hf, 8),
        "stereo_corr": round(corr, 3),
        "lr_balance_db": round(balance, 2),
        "duration_sec": round(mono.size / sr, 2),
    }


def residual_stats(a: np.ndarray, b: np.ndarray) -> dict:
    n = min(a.shape[-1], b.shape[-1])
    a = a[..., :n]
    b = b[..., :n]
    # align channels
    ch = min(a.shape[0], b.shape[0])
    a, b = a[:ch], b[:ch]
    diff = a - b
    e_a = float(np.mean(a**2) + 1e-12)
    e_d = float(np.mean(diff**2) + 1e-12)
    # how much changed relative to original energy
    change_db = 10.0 * np.log10(e_d / e_a)
    return {
        "change_energy_db": round(change_db, 2),
        "mean_abs_diff": round(float(np.mean(np.abs(diff))), 5),
    }


def load_pair(name: str) -> tuple[np.ndarray, np.ndarray, int]:
    src = SRC / name
    restored = OUT / f"{Path(name).stem}.restored.mp4"
    w = WORK / Path(name).stem
    w.mkdir(parents=True, exist_ok=True)
    a_wav = w / "orig.wav"
    b_wav = w / "rest.wav"
    if not a_wav.exists():
        extract_audio(src, a_wav, sample_rate=48000)
    if not b_wav.exists():
        extract_audio(restored, b_wav, sample_rate=48000)
    a, sr_a = read_audio(a_wav)
    b, sr_b = read_audio(b_wav)
    assert sr_a == sr_b
    return a, b, sr_a


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    batch = json.loads((OUT / "batch_all_report.json").read_text(encoding="utf-8"))
    by_name = {r["input"]: r for r in batch if "input" in r}

    rows = []
    for name in SAMPLES:
        if not (SRC / name).exists() or not (OUT / f"{Path(name).stem}.restored.mp4").exists():
            continue
        print(f"compare {name}")
        a, b, sr = load_pair(name)
        ma, mb = metrics(a, sr), metrics(b, sr)
        res = residual_stats(a, b)
        meta = by_name.get(name, {})
        row = {
            "file": name,
            "dfn": bool(meta.get("dfn")),
            "label": meta.get("label"),
            "speech": meta.get("speech"),
            "stages": meta.get("stages", []),
            "before": ma,
            "after": mb,
            "delta": {
                "lufs": round(mb["lufs"] - ma["lufs"], 2),
                "true_peak_dbtp": round(mb["true_peak_dbtp"] - ma["true_peak_dbtp"], 2),
                "centroid_hz": round(mb["centroid_hz"] - ma["centroid_hz"], 1),
                "hf_ratio": round(mb["hf_ratio"] - ma["hf_ratio"], 4),
                "quiet_hf_energy_ratio": round(
                    (mb["quiet_hf_energy"] + 1e-12) / (ma["quiet_hf_energy"] + 1e-12), 3
                ),
                "clipping_ratio": round(mb["clipping_ratio"] - ma["clipping_ratio"], 5),
            },
            "residual": res,
        }
        rows.append(row)
        print(
            f"  LUFS {ma['lufs']} -> {mb['lufs']} ({row['delta']['lufs']:+.2f}) | "
            f"centroid {ma['centroid_hz']} -> {mb['centroid_hz']} | "
            f"change {res['change_energy_db']} dB | dfn={row['dfn']}"
        )

    # Aggregate from full batch report (stages / dfn only)
    all_rows = [r for r in batch if r.get("sample_count_ok")]
    summary = {
        "total_processed": len(all_rows),
        "dfn_count": sum(1 for r in all_rows if r.get("dfn")),
        "dsp_only_count": sum(1 for r in all_rows if not r.get("dfn")),
        "avg_speech": round(
            float(np.mean([r.get("speech") or 0 for r in all_rows])), 3
        ),
        "common_issues": {},
        "stage_frequency": {},
    }
    for r in all_rows:
        for issue in r.get("issues") or []:
            summary["common_issues"][issue] = summary["common_issues"].get(issue, 0) + 1
        for st in r.get("stages") or []:
            summary["stage_frequency"][st] = summary["stage_frequency"].get(st, 0) + 1

    # Aggregate deltas from detailed sample
    if rows:
        summary["sample_avg_delta_lufs"] = round(float(np.mean([r["delta"]["lufs"] for r in rows])), 2)
        summary["sample_avg_delta_centroid_hz"] = round(
            float(np.mean([r["delta"]["centroid_hz"] for r in rows])), 1
        )
        summary["sample_avg_change_energy_db"] = round(
            float(np.mean([r["residual"]["change_energy_db"] for r in rows])), 2
        )
        summary["sample_avg_quiet_hf_ratio"] = round(
            float(np.mean([r["delta"]["quiet_hf_energy_ratio"] for r in rows])), 3
        )

    payload = {"summary": summary, "samples": rows}
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {REPORT}")


if __name__ == "__main__":
    main()
