"""Loudness measurement and normalization via pyloudnorm."""

from __future__ import annotations

import numpy as np
import pyloudnorm as pyln


def measure_loudness(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    """audio: (channels, samples)."""
    data = audio.T  # pyloudnorm expects (samples, channels)
    meter = pyln.Meter(sample_rate)
    try:
        integrated = float(meter.integrated_loudness(data))
    except Exception:
        integrated = float("-inf")
    peak = float(np.max(np.abs(audio)) + 1e-12)
    true_peak_dbtp = 20.0 * np.log10(peak)
    # Rough LRA proxy using block loudness variance is expensive; placeholder 0
    return {
        "integrated_lufs": integrated if np.isfinite(integrated) else -70.0,
        "lra": 0.0,
        "true_peak_dbtp": float(true_peak_dbtp),
    }


def normalize_loudness(
    audio: np.ndarray,
    sample_rate: int,
    target_lufs: float = -16.0,
) -> np.ndarray:
    data = audio.T
    meter = pyln.Meter(sample_rate)
    try:
        loudness = meter.integrated_loudness(data)
        if not np.isfinite(loudness) or loudness < -70:
            return audio.astype(np.float32)
        out = pyln.normalize.loudness(data, loudness, target_lufs)
    except Exception:
        return audio.astype(np.float32)
    return out.T.astype(np.float32)
