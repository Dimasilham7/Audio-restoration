import numpy as np

from audiorestorer_engine.analysis.spectral import fft_freqs, frame_rms, stft_magnitude, zero_crossing_rate


def test_stft_shape():
    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    mono = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    mag, unit = stft_magnitude(mono, n_fft=2048, hop_length=2048)
    assert mag.shape[0] == 1025
    assert mag.shape[1] > 0
    freqs = fft_freqs(sr, 2048)
    assert freqs.shape[0] == mag.shape[0]
    assert abs(freqs[1] - sr / 2048) < 1e-6


def test_zcr_and_rms():
    x = np.array([1, -1, 1, -1, 1, -1], dtype=np.float32)
    z = zero_crossing_rate(x, frame=4, hop=2)
    assert z > 0.5
    r = frame_rms(x, frame=4, hop=2)
    assert r.size >= 1
