"""Process ALL videos in the Pixel eval dataset."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from audiorestorer_engine.pipeline.restore import process_media
from audiorestorer_engine.schemas import RestorationSettings

DATASET = ROOT / "eval" / "datasets" / "pixel-20261122"
OUT = ROOT / "eval" / "output" / "all"
REPORT = OUT / "batch_all_report.json"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(DATASET.glob("PXL_*.mp4"))
    print(f"Found {len(files)} videos in {DATASET}")
    results: list[dict] = []
    t0 = time.time()

    for i, path in enumerate(files, 1):
        out_path = OUT / f"{path.stem}.restored.mp4"
        print(f"\n[{i}/{len(files)}] {path.name} ({path.stat().st_size / 1e6:.1f} MB)")
        if out_path.exists() and out_path.stat().st_size > 1000:
            print(f"  skip (exists): {out_path.name}")
            results.append({"input": path.name, "output": str(out_path), "skipped": True})
            continue
        started = time.time()
        try:
            report = process_media(
                path,
                out_path,
                settings=RestorationSettings(),
                work_dir=OUT / "work" / path.stem,
            )
            entry = {
                "input": path.name,
                "output": str(out_path),
                "label": report.analysis.timeline[0].label.value if report.analysis.timeline else None,
                "speech": (
                    report.analysis.timeline[0].content.get("speech")
                    if report.analysis.timeline
                    else None
                ),
                "issues": [x.id for x in report.analysis.issues],
                "stages": report.stages_applied,
                "dfn": "denoise_speech" in report.stages_applied,
                "sample_count_ok": report.sample_count_ok,
                "warnings": report.warnings,
                "seconds": round(time.time() - started, 2),
            }
            print(
                f"  ok dfn={entry['dfn']} label={entry['label']} "
                f"speech={entry['speech']:.2f} {entry['seconds']}s"
            )
            results.append(entry)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            results.append({"input": path.name, "error": str(exc), "seconds": round(time.time() - started, 2)})
        REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    ok = sum(1 for r in results if r.get("sample_count_ok") or r.get("skipped"))
    dfn = sum(1 for r in results if r.get("dfn"))
    fail = sum(1 for r in results if r.get("error"))
    print(f"\nDone in {elapsed/60:.1f} min | ok/skip={ok} fail={fail} dfn={dfn}/{len(files)}")
    print(f"Report: {REPORT}")
    print(f"Outputs: {OUT}")


if __name__ == "__main__":
    main()
