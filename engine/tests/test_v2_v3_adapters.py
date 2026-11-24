import pytest

from audiorestorer_engine.adapters import audiosr, demucs


def test_demucs_disabled_by_default():
    assert demucs.is_available() is False
    with pytest.raises(demucs.DemucsUnavailable):
        demucs.separate(__import__("numpy").zeros((2, 1000), dtype="float32"), 48000)


def test_audiosr_disabled_by_default():
    assert audiosr.is_available() is False
    with pytest.raises(audiosr.AudioSRUnavailable):
        audiosr.enhance_bandwidth(__import__("numpy").zeros((2, 1000), dtype="float32"), 48000)
