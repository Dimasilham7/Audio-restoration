#!/usr/bin/env python3
"""Phase 0 unverified checklist — gather evidence and write a report."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "eval" / "reports" / "phase0_research.md"


def check(name: str, ok: bool, detail: str) -> tuple[str, bool, str]:
    print(f"[{'PASS' if ok else 'OPEN'}] {name}: {detail}")
    return name, ok, detail


def main() -> int:
    rows: list[tuple[str, bool, str]] = []

    # DFN CLI present (ONNX parity still open — CLI is chosen path)
    dfn = ROOT / ".models" / "deepfilternet" / "deep-filter.exe"
    dfn2 = ROOT / "apps" / "desktop" / "resources" / "bin" / "deep-filter.exe"
    has_dfn = dfn.is_file() or dfn2.is_file()
    rows.append(
        check(
            "dfn_cli_present",
            has_dfn,
            str(dfn if dfn.is_file() else dfn2),
        )
    )
    rows.append(
        check(
            "dfn_onnx_parity",
            False,
            "OPEN: MVP uses official CLI; ONNX parity vs CLI not measured (deferred)",
        )
    )

    # CUDA / torch
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        rows.append(
            check(
                "torch_cuda",
                True,
                f"torch={torch.__version__} cuda_available={cuda} device={torch.cuda.get_device_name(0) if cuda else 'n/a'}",
            )
        )
        if cuda:
            rows.append(
                check(
                    "sm_86_runtime",
                    True,
                    f"capability={torch.cuda.get_device_capability(0)}",
                )
            )
        else:
            rows.append(check("sm_86_runtime", False, "CUDA not available in this env"))
    except Exception as exc:  # noqa: BLE001
        rows.append(check("torch_cuda", False, f"torch not installed: {exc}"))
        rows.append(check("sm_86_runtime", False, "skipped"))

    # nvidia-smi peak probe
    if shutil.which("nvidia-smi"):
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        )
        rows.append(check("nvidia_smi", proc.returncode == 0, proc.stdout.strip() or proc.stderr[:200]))
    else:
        rows.append(check("nvidia_smi", False, "nvidia-smi not on PATH"))

    # PANNs license note (Zenodo) — network lookup best-effort
    panns_note = (
        "PANNs CNN14 on Zenodo: verify license text before bundling; "
        "default remains unbundled / EfficientAT alternative."
    )
    rows.append(check("panns_license", False, f"OPEN: {panns_note}"))

    # EfficientAT vs PANNs — not run
    rows.append(
        check(
            "efficientat_vs_panns",
            False,
            "OPEN: no local accuracy bake-off yet; keep heuristic content labels in MVP",
        )
    )

    # Demucs concert value
    rows.append(
        check(
            "demucs_concert_value",
            False,
            "OPEN: V2 optional; listening spike not run (adapter scaffolded, disabled by default)",
        )
    )

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 0 research report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Item | Status | Detail |",
        "|------|--------|--------|",
    ]
    for name, ok, detail in rows:
        lines.append(f"| `{name}` | {'EVIDENCE' if ok else 'OPEN'} | {detail.replace('|', '/')} |")
    lines += [
        "",
        "## Decision",
        "",
        "- Keep DeepFilterNet **CLI** for MVP (pip wheel rejected).",
        "- Do not bundle Demucs/AudioSR/PANNs weights until license + value gates pass.",
        "- Torch CUDA remains optional; engine MVP path is CPU DSP + DFN CLI.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
