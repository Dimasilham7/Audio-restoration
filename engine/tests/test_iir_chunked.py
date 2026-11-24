"""Chunked vs full-buffer IIR: max abs diff < 1e-5."""

from __future__ import annotations

import numpy as np
from scipy import signal

from audiorestorer_engine.dsp.streaming import sosfilt_chunked


def test_sosfilt_chunked_matches_full_buffer():
    sr = 48000
    rng = np.random.default_rng(42)
    # Stereo ~2.5 s
    audio = rng.standard_normal((2, int(sr * 2.5))).astype(np.float32) * 0.2
    sos = signal.butter(4, 80.0, btype="highpass", fs=sr, output="sos")

    full = signal.sosfilt(sos, audio, axis=-1).astype(np.float32)
    chunked = sosfilt_chunked(sos, audio, chunk_samples=sr // 2)  # 0.5 s chunks

    diff = float(np.max(np.abs(full.astype(np.float64) - chunked.astype(np.float64))))
    assert diff < 1e-5, f"max abs diff={diff}"


def test_sosfilt_chunked_dc_block_style():
    sr = 48000
    t = np.linspace(0, 3.0, sr * 3, endpoint=False)
    mono = (0.1 + 0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    audio = np.stack([mono, mono])
    sos = signal.butter(2, 20.0, btype="highpass", fs=sr, output="sos")
    full = signal.sosfilt(sos, audio, axis=-1).astype(np.float32)
    chunked = sosfilt_chunked(sos, audio, chunk_samples=10_000)
    diff = float(np.max(np.abs(full - chunked)))
    assert diff < 1e-5, f"max abs diff={diff}"
