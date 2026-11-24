"""Re-process top speech-under-music clips + synthetic noisy speech through DFN."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from audiorestorer_engine.pipeline.restore import process_media
from audiorestorer_engine.schemas import RestorationSettings
from audiorestorer_engine.adapters.deepfilternet import enhance, is_available

DATASET = ROOT / "eval" / "datasets" / "pixel-20261122"
OUT = ROOT / "eval" / "output"

# Highest speech scores from scan
TARGETS = [
    "PXL_20261122_134530298.mp4",
    "PXL_20261122_155218066.mp4",
    "PXL_20261122_135147818.mp4",
    "PXL_20261122_134131959.mp4",
    "PXL_20261122_144902594.mp4",
]


def make_noisy_speech() -> Path:
    """Synthetic: tone bursts (speech-like) + noise for DFN smoke through pipeline."""
    sr = 48000
    t = np.linspace(0, 4.0, sr * 4, endpoint=False)
    # amplitude-modulated tones ~ formant-ish
    speech = 0.25 * np.sin(2 * np.pi * 180 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))
    speech += 0.12 * np.sin(2 * np.pi * 900 * t) * (speech > 0)
    noise = 0.08 * np.random.randn(t.size)
    mono = (speech + noise).astype(np.float32)
    stereo = np.stack([mono, mono], axis=1)
    path = OUT / "synthetic_noisy_speech.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), stereo, sr)
    return path


def main() -> None:
    assert is_available(), "DeepFilterNet CLI missing"
    OUT.mkdir(parents=True, exist_ok=True)
    results = []

    # 1) Direct adapter smoke
    synth = make_noisy_speech()
    audio, sr = sf.read(str(synth), always_2d=True, dtype="float32")
    wet = enhance(audio.T, sr, atten_lim_db=12.0)
    direct_out = OUT / "synthetic_noisy_speech.dfn.wav"
    sf.write(str(direct_out), wet.T, sr)
    results.append({"input": synth.name, "output": direct_out.name, "mode": "adapter_direct", "dfn": True})

    # 2) Full pipeline on synthetic wav (force DFN on for adapter verification)
    pipe_out = OUT / "synthetic_noisy_speech.restored.wav"
    settings = RestorationSettings(
        module_overrides={
            "denoise_speech": {
                "enabled": True,
                "params": {"atten_lim_db": 12.0, "gate_with_vad": False, "compensate_delay": True},
            }
        }
    )
    report = process_media(synth, pipe_out, settings=settings, work_dir=OUT / "work" / "synth")
    results.append(
        {
            "input": synth.name,
            "output": str(pipe_out),
            "mode": "pipeline",
            "stages": report.stages_applied,
            "dfn": "denoise_speech" in report.stages_applied,
            "label": report.analysis.timeline[0].label.value,
            "speech": report.analysis.timeline[0].content.get("speech"),
            "sample_count_ok": report.sample_count_ok,
        }
    )
    print("SYNTH", results[-1])

    # 3) Real Pixel clips (expect gated DFN now that threshold is 0.22)
    for name in TARGETS:
        path = DATASET / name
        out_path = OUT / f"{path.stem}.dfn.restored.mp4"
        print(f"\n=== {name} ===")
        report = process_media(
            path,
            out_path,
            settings=RestorationSettings(),
            work_dir=OUT / "work" / f"{path.stem}_dfn",
        )
        entry = {
            "input": name,
            "output": str(out_path),
            "mode": "pipeline",
            "stages": report.stages_applied,
            "dfn": "denoise_speech" in report.stages_applied,
            "label": report.analysis.timeline[0].label.value,
            "speech": report.analysis.timeline[0].content.get("speech"),
            "sample_count_ok": report.sample_count_ok,
            "issues": [i.id for i in report.analysis.issues],
        }
        print(entry)
        results.append(entry)

    report_path = OUT / "batch_dfn_report.json"
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {report_path}")
    print(f"DFN used on {sum(1 for r in results if r.get('dfn'))}/{len(results)}")


if __name__ == "__main__":
    main()
