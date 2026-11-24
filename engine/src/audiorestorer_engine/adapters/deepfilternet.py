"""DeepFilterNet3 adapter via official Windows/Linux CLI (not the stale pip wheel)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

import soundfile as sf

from audiorestorer_engine.io.audio import match_length, read_audio
from audiorestorer_engine.pipeline.progress import CancelledError


def _write_pcm16_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write (channels, samples) float32 as PCM_16 WAV for the DFN CLI."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(audio, -1.0, 1.0)
    if data.ndim == 1:
        out = data
    else:
        out = data.T
    sf.write(str(path), out, sample_rate, subtype="PCM_16")

DFN_SR = 48000


class DeepFilterNetError(RuntimeError):
    pass


def default_exe_path() -> Path | None:
    from audiorestorer_engine.config import deep_filter_path

    return deep_filter_path()


def is_available() -> bool:
    return default_exe_path() is not None


def enhance(
    audio: np.ndarray,
    sample_rate: int,
    *,
    atten_lim_db: float = 12.0,
    compensate_delay: bool = True,
    work_dir: str | Path | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> np.ndarray:
    """
    Run DeepFilterNet3 on float32 audio (channels, samples).

    Resamples to 48 kHz for the CLI, then back. Preserves channel count.
    """
    exe = default_exe_path()
    if exe is None:
        raise DeepFilterNetError(
            "DeepFilterNet CLI not found. Set AUDIORESTORER_DFN_EXE or place "
            "binary at .models/deepfilternet/deep-filter.exe"
        )

    atten_lim_db = float(np.clip(atten_lim_db, 0.0, 100.0))
    original = audio.astype(np.float32, copy=False)
    n_orig = original.shape[-1]

    # Resample to 48 kHz if needed
    if sample_rate != DFN_SR:
        from scipy import signal as sig

        gcd = np.gcd(sample_rate, DFN_SR)
        up, down = DFN_SR // gcd, sample_rate // gcd
        work = np.stack(
            [sig.resample_poly(ch, up, down).astype(np.float32) for ch in original],
            axis=0,
        )
    else:
        work = original.copy()

    own_tmp = work_dir is None
    root = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="dfn_"))
    in_dir = root / "in"
    out_dir = root / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    in_wav = in_dir / "audio.wav"
    out_wav = out_dir / "audio.wav"

    try:
        # Official CLI is validated with PCM s16 WAV
        _write_pcm16_wav(in_wav, np.clip(work, -1.0, 1.0), DFN_SR)

        cmd = [
            str(exe),
            "-o",
            str(out_dir),
            "-a",
            str(atten_lim_db),
        ]
        if compensate_delay:
            cmd.append("-D")
        cmd.append(str(in_wav))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        while proc.poll() is None:
            if is_cancelled and is_cancelled():
                proc.kill()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                raise CancelledError("DeepFilterNet cancelled")
            time.sleep(0.05)
        stderr = proc.stderr.read() if proc.stderr else ""
        if proc.returncode != 0 or not out_wav.is_file():
            raise DeepFilterNetError(
                f"DeepFilterNet failed ({proc.returncode}): {stderr[-2000:]}"
            )

        enhanced, sr = read_audio(out_wav)
        if sr != DFN_SR:
            raise DeepFilterNetError(f"Unexpected DFN sample rate {sr}")

        # Match working length at 48 kHz
        enhanced = match_length(enhanced, work.shape[-1])

        # Back to original rate
        if sample_rate != DFN_SR:
            from scipy import signal as sig

            gcd = np.gcd(DFN_SR, sample_rate)
            up, down = sample_rate // gcd, DFN_SR // gcd
            enhanced = np.stack(
                [sig.resample_poly(ch, up, down).astype(np.float32) for ch in enhanced],
                axis=0,
            )

        enhanced = match_length(enhanced, n_orig)
        if enhanced.shape[0] != original.shape[0]:
            # Channel mismatch — down/up mix conservatively
            if enhanced.shape[0] == 1 and original.shape[0] > 1:
                enhanced = np.repeat(enhanced, original.shape[0], axis=0)
            else:
                enhanced = enhanced[: original.shape[0]]
                enhanced = match_length(enhanced, n_orig)
        return enhanced.astype(np.float32)
    finally:
        if own_tmp:
            shutil.rmtree(root, ignore_errors=True)


def speech_activity_mask(
    audio: np.ndarray,
    sample_rate: int,
    *,
    frame_ms: float = 30.0,
    hop_ms: float = 10.0,
) -> np.ndarray:
    """
    Lightweight speech activity mask in [0, 1] per sample (no neural VAD yet).

    Uses frame RMS vs noise floor + zero-crossing rate heuristic.
    Good enough to protect music beds in mixed content.
    """
    mono = np.mean(audio, axis=0) if audio.ndim > 1 else audio
    frame = max(1, int(sample_rate * frame_ms / 1000.0))
    hop = max(1, int(sample_rate * hop_ms / 1000.0))
    if mono.size < frame:
        return np.ones(mono.shape[-1], dtype=np.float32)

    # Frame energies
    n_frames = 1 + max(0, (mono.size - frame) // hop)
    energies = np.empty(n_frames, dtype=np.float32)
    zcrs = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        start = i * hop
        chunk = mono[start : start + frame]
        energies[i] = float(np.sqrt(np.mean(chunk**2)) + 1e-12)
        zcrs[i] = float(np.mean(np.abs(np.diff(np.sign(chunk)))) * 0.5)

    noise_floor = float(np.percentile(energies, 20))
    snr = energies / (noise_floor + 1e-12)
    # Speech-ish: elevated energy and moderate ZCR
    speech_like = (snr > 2.0) & (zcrs > 0.02) & (zcrs < 0.35)
    raw = speech_like.astype(np.float32)

    # Smooth and upsample to samples
    kernel = np.ones(5, dtype=np.float32) / 5.0
    raw = np.convolve(raw, kernel, mode="same")
    sample_idx = np.arange(mono.size)
    frame_centers = (np.arange(n_frames) * hop + frame / 2.0).clip(0, mono.size - 1)
    mask = np.interp(sample_idx, frame_centers, raw).astype(np.float32)
    return np.clip(mask, 0.0, 1.0)


def mix_wet_dry(
    dry: np.ndarray,
    wet: np.ndarray,
    mask: np.ndarray | None,
    *,
    wet_gain: float = 1.0,
) -> np.ndarray:
    """Crossfade wet/dry using optional per-sample mask (1 = full wet)."""
    dry = dry.astype(np.float32)
    wet = match_length(wet.astype(np.float32), dry.shape[-1])
    if mask is None:
        return (wet * wet_gain).astype(np.float32)
    m = mask.astype(np.float32)
    if m.ndim == 1:
        m = m[np.newaxis, :]
    return (wet * m * wet_gain + dry * (1.0 - m)).astype(np.float32)
