"""Audio file I/O helpers (float32 WAV / RF64 via soundfile)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def read_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Return float32 array shaped (channels, samples) and sample rate."""
    data, sr = sf.read(str(path), always_2d=True, dtype="float32")
    # soundfile returns (samples, channels)
    audio = data.T.copy()
    return audio, int(sr)


def write_audio(path: str | Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write float32 WAV. Accepts (channels, samples) or (samples,)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio.ndim == 1:
        data = audio
    else:
        data = audio.T
    sf.write(str(path), data, sample_rate, subtype="FLOAT")


def ensure_channels_first(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio[np.newaxis, :]
    if audio.shape[0] <= 8 and audio.shape[0] < audio.shape[-1]:
        return audio
    return audio.T


def match_length(audio: np.ndarray, target_samples: int) -> np.ndarray:
    """Pad or trim along the last axis to target_samples."""
    current = audio.shape[-1]
    if current == target_samples:
        return audio
    if current > target_samples:
        return audio[..., :target_samples]
    pad = target_samples - current
    return np.pad(audio, [(0, 0)] * (audio.ndim - 1) + [(0, pad)])
