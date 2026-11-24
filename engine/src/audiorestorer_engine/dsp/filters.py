"""Safe-bound DSP building blocks."""

from __future__ import annotations

import numpy as np
from scipy import signal


def dc_block(audio: np.ndarray, sample_rate: int, cutoff_hz: float = 20.0) -> np.ndarray:
    sos = signal.butter(2, cutoff_hz, btype="highpass", fs=sample_rate, output="sos")
    return signal.sosfilt(sos, audio, axis=-1).astype(np.float32)


def highpass(audio: np.ndarray, sample_rate: int, cutoff_hz: float, order: int = 2) -> np.ndarray:
    cutoff_hz = float(np.clip(cutoff_hz, 20.0, sample_rate * 0.45))
    sos = signal.butter(order, cutoff_hz, btype="highpass", fs=sample_rate, output="sos")
    return signal.sosfilt(sos, audio, axis=-1).astype(np.float32)


def peaking_eq(
    audio: np.ndarray,
    sample_rate: int,
    freq: float,
    gain_db: float,
    q: float = 1.0,
) -> np.ndarray:
    gain_db = float(np.clip(gain_db, -18.0, 9.0))
    freq = float(np.clip(freq, 20.0, sample_rate * 0.45))
    q = float(np.clip(q, 0.1, 10.0))
    b, a = signal.iirpeak(freq, q, fs=sample_rate)
    # iirpeak is unity gain notch-like; use biquad peaking via bilinear design
    w0 = 2 * np.pi * freq / sample_rate
    alpha = np.sin(w0) / (2 * q)
    a_gain = 10 ** (gain_db / 40)
    b0 = 1 + alpha * a_gain
    b1 = -2 * np.cos(w0)
    b2 = 1 - alpha * a_gain
    a0 = 1 + alpha / a_gain
    a1 = -2 * np.cos(w0)
    a2 = 1 - alpha / a_gain
    b = np.array([b0, b1, b2]) / a0
    a = np.array([1.0, a1 / a0, a2 / a0])
    return signal.lfilter(b, a, audio, axis=-1).astype(np.float32)


def high_shelf(
    audio: np.ndarray,
    sample_rate: int,
    freq: float,
    gain_db: float,
) -> np.ndarray:
    gain_db = float(np.clip(gain_db, -18.0, 12.0))
    freq = float(np.clip(freq, 1000.0, sample_rate * 0.45))
    a_gain = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * freq / sample_rate
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    s = 1.0
    alpha = sin_w0 / 2 * np.sqrt((a_gain + 1 / a_gain) * (1 / s - 1) + 2)
    two_sqrt_a_alpha = 2 * np.sqrt(a_gain) * alpha

    b0 = a_gain * ((a_gain + 1) + (a_gain - 1) * cos_w0 + two_sqrt_a_alpha)
    b1 = -2 * a_gain * ((a_gain - 1) + (a_gain + 1) * cos_w0)
    b2 = a_gain * ((a_gain + 1) + (a_gain - 1) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a_gain + 1) - (a_gain - 1) * cos_w0 + two_sqrt_a_alpha
    a1 = 2 * ((a_gain - 1) - (a_gain + 1) * cos_w0)
    a2 = (a_gain + 1) - (a_gain - 1) * cos_w0 - two_sqrt_a_alpha

    b = np.array([b0, b1, b2]) / a0
    a = np.array([1.0, a1 / a0, a2 / a0])
    return signal.lfilter(b, a, audio, axis=-1).astype(np.float32)


def notch_comb(
    audio: np.ndarray,
    sample_rate: int,
    f0: float,
    harmonics: int = 5,
    q: float = 30.0,
) -> np.ndarray:
    out = audio.astype(np.float32, copy=True)
    q = float(np.clip(q, 20.0, 60.0))
    harmonics = int(np.clip(harmonics, 1, 10))
    for n in range(1, harmonics + 1):
        freq = f0 * n
        if freq >= sample_rate * 0.45:
            break
        b, a = signal.iirnotch(freq, q, fs=sample_rate)
        out = signal.lfilter(b, a, out, axis=-1).astype(np.float32)
    return out


def soft_declip(audio: np.ndarray, threshold: float = 0.99) -> np.ndarray:
    """Mild AR-like repair: lerp clipped runs toward local median neighborhood."""
    out = audio.astype(np.float32, copy=True)
    for ch in range(out.shape[0]):
        x = out[ch]
        mask = np.abs(x) >= threshold
        if not np.any(mask):
            continue
        # Simple cubic interpolation across short clipped runs
        idx = np.arange(x.size)
        good = ~mask
        if good.sum() < 8:
            continue
        x_fixed = np.interp(idx, idx[good], x[good]).astype(np.float32)
        # Only replace clipped samples
        x[mask] = x_fixed[mask]
        out[ch] = x
    return out


def true_peak_limit(audio: np.ndarray, ceiling_dbtp: float = -1.0) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) + 1e-12
    ceiling = 10 ** (ceiling_dbtp / 20.0)
    if peak <= ceiling:
        return audio.astype(np.float32)
    return (audio * (ceiling / peak)).astype(np.float32)


def normalize_peak(audio: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) + 1e-12
    return (audio * (target_peak / peak)).astype(np.float32)


def stereo_width(audio: np.ndarray, width: float = 1.0) -> np.ndarray:
    if audio.shape[0] < 2:
        return audio
    width = float(np.clip(width, 0.5, 1.5))
    left, right = audio[0], audio[1]
    mid = (left + right) * 0.5
    side = (left - right) * 0.5
    side *= width
    out = np.stack([mid + side, mid - side], axis=0)
    return out.astype(np.float32)


def balance_lr(audio: np.ndarray, balance_db: float) -> np.ndarray:
    """Apply opposite gains to L/R to correct imbalance. balance_db is L-R."""
    if audio.shape[0] < 2:
        return audio
    # If L is hotter by +balance_db, attenuate L / boost R by half
    half = balance_db / 2.0
    l_gain = 10 ** ((-half) / 20.0)
    r_gain = 10 ** ((half) / 20.0)
    out = audio.copy()
    out[0] *= l_gain
    out[1] *= r_gain
    return out.astype(np.float32)
