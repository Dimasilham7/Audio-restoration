#!/usr/bin/env python3
"""Batch analyze/process Pixel eval clips."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running without install
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from audiorestorer_engine.pipeline.restore import analyze_media, process_media
from audiorestorer_engine.schemas import RestorationSettings

DATASET = ROOT / "eval" / "datasets" / "pixel-20261122"
OUT = ROOT / "eval" / "output"
REPORT = OUT / "batch_report.json"


def pick_targets(limit: int = 8) -> list[Path]:
    """Prefer mid-length files: skip tiny (<3s) and huge (>120MB decode time)."""
    files = sorted(DATASET.glob("PXL_*.mp4"), key=lambda p: p.stat().st_size)
    # Skip smallest (often <5s) and take a spread of sizes
    mid = [p for p in files if 20_000_000 < p.stat().st_size < 200_000_000]
    if len(mid) < limit:
        mid = [p for p in files if p.stat().st_size > 15_000_000][: limit + 4]
    # diversify: take every n-th
    if len(mid) > limit:
        step = max(1, len(mid) // limit)
        mid = mid[::step][:limit]
    return mid[:limit]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = pick_targets(8)
    print(f"Selected {len(targets)} files")
    results = []

    for path in targets:
        print(f"\n=== {path.name} ({path.stat().st_size / 1e6:.1f} MB) ===")
        try:
            analysis_report = analyze_media(path, work_dir=OUT / "work" / path.stem)
            label = analysis_report.analysis.timeline[0].label.value
            issues = [i.id for i in analysis_report.analysis.issues]
            stages = [s.id.value for s in analysis_report.plan.stages if s.enabled]
            print(f"  label={label} issues={issues}")
            print(f"  plan={stages}")

            out_path = OUT / f"{path.stem}.restored.mp4"
            report = process_media(
                path,
                out_path,
                settings=RestorationSettings(),
                work_dir=OUT / "work" / path.stem,
            )
            entry = {
                "input": path.name,
                "output": str(out_path),
                "label": label,
                "issues": issues,
                "stages_applied": report.stages_applied,
                "sample_count_ok": report.sample_count_ok,
                "warnings": report.warnings,
                "dfn": "denoise_speech" in report.stages_applied,
            }
            print(f"  -> {out_path.name} dfn={entry['dfn']} ok={entry['sample_count_ok']}")
            results.append(entry)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            results.append({"input": path.name, "error": str(exc)})

    REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {REPORT}")
    ok = sum(1 for r in results if r.get("sample_count_ok"))
    dfn = sum(1 for r in results if r.get("dfn"))
    print(f"Success {ok}/{len(results)}, DeepFilterNet used on {dfn}")


if __name__ == "__main__":
    main()
