#!/usr/bin/env python3
"""Run integration acceptance against real Pixel clips + live engine HTTP API.

Writes eval/reports/acceptance_report.md with pass/fail.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine"
DATASET = ROOT / "eval" / "datasets" / "pixel-20261122"
OUT_DIR = ROOT / "eval" / "output" / "acceptance"
REPORT = ROOT / "eval" / "reports" / "acceptance_report.md"
BIN = ROOT / "apps" / "desktop" / "resources" / "bin"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    if BIN.is_dir():
        env["AUDIORESTORER_BIN_DIR"] = str(BIN)
        env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH', '')}"
    dfn = ROOT / ".models" / "deepfilternet" / "deep-filter.exe"
    if dfn.is_file():
        env["AUDIORESTORER_DFN_EXE"] = str(dfn)
    elif (BIN / "deep-filter.exe").is_file():
        env["AUDIORESTORER_DFN_EXE"] = str(BIN / "deep-filter.exe")
    return env


results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")


def pick_clips(n: int = 3) -> list[Path]:
    clips = sorted(DATASET.glob("*.mp4"), key=lambda p: p.stat().st_size)
    return clips[:n]


def ffprobe_duration(path: Path) -> float:
    ffprobe = os.environ.get("AUDIORESTORER_FFPROBE") or "ffprobe"
    if BIN.is_dir() and (BIN / "ffprobe.exe").is_file():
        ffprobe = str(BIN / "ffprobe.exe")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_env(),
    )
    data = json.loads(proc.stdout or "{}")
    return float(data.get("format", {}).get("duration") or 0.0)


def test_media_hard_gates() -> None:
    sys.path.insert(0, str(ENGINE / "src"))
    from audiorestorer_engine.pipeline.restore import process_media
    from audiorestorer_engine.schemas import RestorationSettings

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clips = pick_clips(3)
    if not clips:
        record("media_clips_present", False, f"missing {DATASET}")
        return
    record("media_clips_present", True, f"{len(clips)} clips")

    for clip in clips:
        out = OUT_DIR / f"{clip.stem}.restored.mp4"
        work = OUT_DIR / f"work_{clip.stem}"
        try:
            report = process_media(
                clip,
                out,
                settings=RestorationSettings(loudness_target_lufs=-16.0),
                work_dir=work,
            )
            ok_count = report.sample_count_ok
            record(f"gate1_sample_count:{clip.name}", ok_count, f"stages={report.stages_applied}")

            # NaN check on restored wav
            from audiorestorer_engine.io.audio import read_audio

            audio, _ = read_audio(report.output_audio_path)
            finite = bool(np.isfinite(audio).all())
            record(f"gate6_finite:{clip.name}", finite, f"shape={audio.shape}")

            # Duration drift (A/V remux proxy)
            din = ffprobe_duration(clip)
            dout = ffprobe_duration(Path(report.output_media_path or out))
            drift = abs(din - dout)
            record(
                f"gate2_duration_drift:{clip.name}",
                drift <= 0.05,
                f"in={din:.3f}s out={dout:.3f}s drift={drift:.4f}s",
            )

            # Loudness if loudness stage applied
            from audiorestorer_engine.dsp.loudness import measure_loudness

            if "loudness" in report.stages_applied:
                loud = measure_loudness(audio, report.analysis.sample_rate)["integrated_lufs"]
                ok = abs(loud - (-16.0)) <= 0.5 or abs(loud - report.settings.loudness_target_lufs) <= 0.5
                # Note: measure after remux may differ; use restored wav
                record(f"gate4_loudness:{clip.name}", ok, f"LUFS={loud:.2f}")

            if "limiter" in report.stages_applied:
                peak = float(np.max(np.abs(audio)) + 1e-12)
                peak_db = 20 * np.log10(peak)
                record(f"gate3_true_peak:{clip.name}", peak_db <= -1.0 + 0.15, f"TP={peak_db:.2f} dB")

            # Music safety on plan
            label = report.analysis.timeline[0].label.value if report.analysis.timeline else ""
            speech_p = float(report.analysis.timeline[0].content.get("speech", 0) if report.analysis.timeline else 0)
            if label == "music_dominant" and speech_p < 0.22:
                applied = "denoise_speech" in report.stages_applied
                record(f"gate13_music_no_dfn:{clip.name}", not applied, f"label={label} speech={speech_p:.2f}")
        except Exception as exc:  # noqa: BLE001
            record(f"process:{clip.name}", False, str(exc))


def test_cancel_latency() -> None:
    sys.path.insert(0, str(ENGINE / "src"))
    from audiorestorer_engine.pipeline.progress import CancelledError, JobContext
    from audiorestorer_engine.pipeline.restore import process_media
    from audiorestorer_engine.schemas import RestorationSettings

    clips = pick_clips(1)
    if not clips:
        record("cancel_latency", False, "no clips")
        return
    clip = max(DATASET.glob("*.mp4"), key=lambda p: p.stat().st_size) if DATASET.exists() else clips[0]
    # Prefer a medium clip if available
    med = sorted(DATASET.glob("*.mp4"), key=lambda p: p.stat().st_size)
    clip = med[len(med) // 2] if med else clips[0]

    flag = {"c": False}
    cancel_at = {"t": None}

    def is_cancelled() -> bool:
        return flag["c"]

    def on_progress(p: float, stage: str, message: str | None) -> None:
        # Cancel once processing is clearly underway
        if p >= 0.2 and not flag["c"]:
            flag["c"] = True
            cancel_at["t"] = time.perf_counter()

    t0 = time.perf_counter()
    try:
        process_media(
            clip,
            OUT_DIR / "cancel_test.mp4",
            settings=RestorationSettings(),
            work_dir=OUT_DIR / "cancel_work",
            ctx=JobContext(progress=on_progress, is_cancelled=is_cancelled),
        )
        elapsed = time.perf_counter() - t0
        record(
            "cancel_latency",
            False,
            f"job finished without CancelledError in {elapsed:.2f}s",
        )
    except CancelledError:
        elapsed = time.perf_counter() - t0
        after_cancel = (time.perf_counter() - cancel_at["t"]) if cancel_at["t"] else elapsed
        record("cancel_latency", after_cancel <= 2.0, f"stopped {after_cancel:.2f}s after cancel")
    except Exception as exc:  # noqa: BLE001
        record("cancel_latency", False, str(exc))


def test_http_api() -> None:
    token = "acceptance-token"
    env = _env()
    env["AUDIORESTORER_TOKEN"] = token
    # Start serve
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "audiorestorer-engine",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--token",
            token,
        ],
        cwd=str(ENGINE),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    port = None
    assert proc.stdout is not None
    deadline = time.time() + 45
    buf = ""
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        buf += line
        if "READY port=" in line:
            port = int(line.strip().split("READY port=")[1].split()[0])
            break
    if not port:
        record("api_ready", False, f"no READY; out={buf[-500:]}")
        proc.kill()
        return
    record("api_ready", True, f"port={port}")
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=120.0) as client:
            h = client.get(f"{base}/v1/health")
            record("api_health", h.status_code == 200, h.text)

            # unauthorized
            bad = client.get(f"{base}/v1/capabilities")
            record("api_auth_required", bad.status_code == 401, f"status={bad.status_code}")

            caps = client.get(f"{base}/v1/capabilities", headers=headers)
            record("api_capabilities", caps.status_code == 200, caps.text[:200])

            clips = pick_clips(1)
            if clips:
                payload = {
                    "kind": "analyze",
                    "media_path": str(clips[0]),
                }
                job = client.post(f"{base}/v1/jobs", headers=headers, json=payload)
                record("api_create_job", job.status_code == 200, job.text[:300])
                if job.status_code == 200:
                    jid = job.json()["id"]
                    # poll
                    final = None
                    for _ in range(120):
                        g = client.get(f"{base}/v1/jobs/{jid}", headers=headers)
                        final = g.json()
                        if final.get("state") in ("completed", "failed", "cancelled"):
                            break
                        time.sleep(0.25)
                    record(
                        "api_job_complete",
                        bool(final) and final.get("state") == "completed",
                        json.dumps(final or {})[:400],
                    )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_electron_security_smoke() -> None:
    # Static checks against packaged / source main
    main_src = (ROOT / "apps" / "desktop" / "src" / "main" / "index.ts").read_text(encoding="utf-8")
    record("sec_sandbox_true", "sandbox: true" in main_src, "sandbox flag in main")
    record("sec_node_integration_false", "nodeIntegration: false" in main_src, "nodeIntegration off")
    record("sec_context_isolation", "contextIsolation: true" in main_src, "contextIsolation on")
    record("sec_media_protocol", 'scheme: "media"' in main_src or "media://" in main_src, "media protocol registered")


def test_portable_layout() -> None:
    unpacked = ROOT / "apps" / "desktop" / "release" / "win-unpacked"
    checks = {
        "portable_exe": unpacked / "AudioRestorer AI.exe",
        "engine_exe": unpacked / "resources" / "engine" / "audiorestorer-engine.exe",
        "ffmpeg": unpacked / "resources" / "bin" / "ffmpeg.exe",
        "ffprobe": unpacked / "resources" / "bin" / "ffprobe.exe",
        "dfn": unpacked / "resources" / "bin" / "deep-filter.exe",
        "licenses": unpacked / "resources" / "licenses" / "THIRD_PARTY.txt",
    }
    for name, path in checks.items():
        record(f"product_gate_layout:{name}", path.is_file(), str(path))


def write_report() -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    lines = [
        "# Acceptance report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Summary: **{passed} passed**, **{failed} failed** / {len(results)} checks",
        "",
        "| Check | Result | Detail |",
        "|-------|--------|--------|",
    ]
    for name, ok, detail in results:
        lines.append(f"| `{name}` | {'PASS' if ok else 'FAIL'} | {detail.replace('|', '/')} |")
    lines += [
        "",
        "## Not run / blocked (need more product work)",
        "",
        "- Full 9-screen UI + uncertainty UX (`UI_UX_SPECIFICATION`) — UI is batch + A/B only",
        "- SQLite schema/migrations (`DATABASE_SCHEMA`) — not implemented in app yet",
        "- Formal PESQ/STOI/DNSMOS + blind preference listening panel",
        "- 2-hour stereo fixture OOM gate (too long for CI; not executed)",
        "- Windows Sandbox clean install (feature requires elevation; checklist only)",
        "- V2/V3 Demucs/AudioSR — deferred by design",
        "- Phase 0 unverified: DFN ONNX parity, Torch CUDA VRAM, PANNs license, EfficientAT, Demucs concert value",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {REPORT}")


def main() -> int:
    os.chdir(ROOT)
    print("== Electron security static ==")
    test_electron_security_smoke()
    print("== Portable layout ==")
    test_portable_layout()
    print("== Unit hard gates (pytest) ==")
    proc = subprocess.run(
        ["uv", "run", "pytest", "-q", "tests/test_hard_gates.py", "tests/test_planner.py", "tests/test_spectral.py"],
        cwd=str(ENGINE),
        env=_env(),
    )
    record("pytest_hard_gates_suite", proc.returncode == 0, f"exit={proc.returncode}")
    print("== Media integration ==")
    test_media_hard_gates()
    print("== Cancel ==")
    test_cancel_latency()
    print("== HTTP API ==")
    test_http_api()
    write_report()
    failed = sum(1 for _, ok, _ in results if not ok)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
