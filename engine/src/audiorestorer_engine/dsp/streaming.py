"""Chunked streaming DSP helpers (stateful IIR)."""

from __future__ import annotations

import numpy as np
from scipy import signal


def sosfilt_chunked(
    sos: np.ndarray,
    audio: np.ndarray,
    *,
    chunk_samples: int = 48000,
) -> np.ndarray:
    """Apply SOS filter in chunks with carried ``zi`` — bit-identical to full ``sosfilt``."""
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]
        squeeze = True
    else:
        squeeze = False

    n_sections = sos.shape[0]
    channels, n = audio.shape
    out = np.empty_like(audio, dtype=np.float64)
    # Per-channel state: (n_sections, 2)
    zi = signal.sosfilt_zi(sos)  # (n_sections, 2)

    for ch in range(channels):
        z = zi * 0.0  # start from zero (same as default sosfilt)
        # Actually sosfilt default zi is zeros; sosfilt_zi is steady-state for step.
        z = np.zeros_like(zi)
        for start in range(0, n, chunk_samples):
            end = min(n, start + chunk_samples)
            chunk = audio[ch, start:end].astype(np.float64, copy=False)
            y, z = signal.sosfilt(sos, chunk, zi=z)
            out[ch, start:end] = y

    if squeeze:
        return out[0].astype(np.float32)
    return out.astype(np.float32)
