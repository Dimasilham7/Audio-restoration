"""Numpy/scipy spectral helpers (no librosa/numba)."""

from __future__ import annotations

import numpy as np


def stft_magnitude(
    mono: np.ndarray,
    *,
    n_fft: int = 2048,
    hop_length: int = 2048,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (magnitude [freq, frames], freqs for sample_rate later via fft_freqs)."""
    if mono.size < n_fft:
        mono = np.pad(mono, (0, n_fft - mono.size))
    window = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + max(0, (mono.size - n_fft) // hop_length)
    mag = np.empty((n_fft // 2 + 1, n_frames), dtype=np.float32)
    for i in range(n_frames):
        start = i * hop_length
        frame = mono[start : start + n_fft]
        if frame.size < n_fft:
            frame = np.pad(frame, (0, n_fft - frame.size))
        spec = np.fft.rfft(frame * window)
        mag[:, i] = np.abs(spec).astype(np.float32)
    return mag, np.fft.rfftfreq(n_fft)  # unit freqs; scale by sr outside


def fft_freqs(sample_rate: int, n_fft: int = 2048) -> np.ndarray:
    return np.fft.rfftfreq(n_fft, d=1.0 / sample_rate).astype(np.float64)


def frame_rms(mono: np.ndarray, *, frame: int = 2048, hop: int = 2048) -> np.ndarray:
    if mono.size < frame:
        return np.array([float(np.sqrt(np.mean(mono**2) + 1e-12))], dtype=np.float32)
    n_frames = 1 + max(0, (mono.size - frame) // hop)
    out = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        chunk = mono[i * hop : i * hop + frame]
        out[i] = float(np.sqrt(np.mean(chunk**2) + 1e-12))
    return out


def zero_crossing_rate(mono: np.ndarray, *, frame: int = 2048, hop: int = 2048) -> float:
    if mono.size < 2:
        return 0.0
    if mono.size < frame:
        return float(np.mean(np.abs(np.diff(np.signbit(mono).astype(np.int8)))))
    n_frames = 1 + max(0, (mono.size - frame) // hop)
    rates = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        chunk = mono[i * hop : i * hop + frame]
        rates[i] = float(np.mean(np.abs(np.diff(np.signbit(chunk).astype(np.int8)))))
    return float(np.mean(rates))
