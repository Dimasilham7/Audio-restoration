from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from audiorestorer_engine.pipeline.restore import analyze_media

root = ROOT / "eval" / "datasets" / "pixel-20261122"
out = ROOT / "eval" / "output" / "work"
files = sorted(root.glob("PXL_*.mp4"), key=lambda p: p.stat().st_size)
picks = files[5:35]
rows = []
for p in picks:
    r = analyze_media(p, work_dir=out / f"scan_{p.stem}")
    t = r.analysis.timeline[0]
    rows.append(
        (
            float(t.content.get("speech", 0)),
            t.label.value,
            p.name,
            p.stat().st_size / 1e6,
        )
    )
rows.sort(reverse=True)
for speech, label, name, mb in rows:
    print(f"{speech:.2f} {label:16} {mb:6.1f}MB {name}")
