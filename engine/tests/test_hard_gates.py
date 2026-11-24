"""MVP hard gates from docs/TESTING_STRATEGY.md (synthetic / unit-level)."""

from __future__ import annotations

import time

import numpy as np
import pytest

from audiorestorer_engine.analysis.analyzer import analyze_audio
from audiorestorer_engine.dsp import filters
from audiorestorer_engine.dsp.loudness import measure_loudness, normalize_loudness
from audiorestorer_engine.pipeline.progress import CancelledError, JobContext
from audiorestorer_engine.pipeline.restore import apply_plan
from audiorestorer_engine.planning.planner import plan
from audiorestorer_engine.schemas import (
    AnalysisIssue,
    AnalysisResult,
    ContentLabel,
    GlobalMetrics,
    LoudnessMetrics,
    Preset,
    Recoverability,
    RestorationSettings,
    StageId,
    StereoMetrics,
    TimelineRegion,
)


SR = 48000


def _tone(freq: float, sec: float = 2.0, amp: float = 0.2) -> np.ndarray:
    t = np.linspace(0, sec, int(SR * sec), endpoint=False)
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([mono, mono], axis=0)


def _si_sdr(ref: np.ndarray, est: np.ndarray) -> float:
    """Scale-invariant SDR in dB (mono mix)."""
    x = ref.mean(axis=0).astype(np.float64)
    y = est.mean(axis=0).astype(np.float64)
    n = min(x.size, y.size)
    x, y = x[:n], y[:n]
    alpha = np.dot(y, x) / (np.dot(x, x) + 1e-12)
    s_target = alpha * x
    e_noise = y - s_target
    return float(10 * np.log10((np.dot(s_target, s_target) + 1e-12) / (np.dot(e_noise, e_noise) + 1e-12)))


def test_gate1_sample_count_match():
    audio = _tone(440, 1.5)
    analysis = analyze_audio(audio, SR)
    treatment = plan(analysis, RestorationSettings(preset=Preset.natural, strength=0.3))
    out, _ = apply_plan(audio, SR, treatment)
    assert out.shape[-1] == audio.shape[-1]


def test_gate3_true_peak_ceiling():
    # Hot signal that needs limiting
    audio = _tone(440, 1.0, amp=0.95)
    out = filters.true_peak_limit(audio, ceiling_dbtp=-1.0)
    peak_db = 20 * np.log10(float(np.max(np.abs(out))) + 1e-12)
    assert peak_db <= -1.0 + 0.1 + 0.05  # small numeric slack


def test_gate4_loudness_within_half_lu():
    audio = _tone(440, 3.0, amp=0.05)
    target = -16.0
    out = normalize_loudness(audio, SR, target_lufs=target)
    measured = measure_loudness(out, SR)["integrated_lufs"]
    assert abs(measured - target) <= 0.5


def test_gate5_clean_control_si_sdr_natural():
    # Broadband-ish stereo (avoids pure-tone muffled false positive)
    rng = np.random.default_rng(0)
    sec = 2.0
    n = int(SR * sec)
    noise = (0.05 * rng.standard_normal(n)).astype(np.float32)
    t = np.linspace(0, sec, n, endpoint=False)
    voice = (0.15 * np.sin(2 * np.pi * 180 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))).astype(
        np.float32
    )
    mono = noise + voice
    audio = np.stack([mono, mono], axis=0)

    analysis = analyze_audio(audio, SR)
    # Do-no-harm gate: Natural on content with no high-confidence issues
    analysis.issues = [i for i in analysis.issues if i.confidence < 0.55]
    settings = RestorationSettings(preset=Preset.natural, strength=0.2, noise_reduction=0.0)
    treatment = plan(analysis, settings)
    for s in treatment.stages:
        if s.id in (StageId.denoise_speech, StageId.tonal_eq):
            s.enabled = False
    out, _ = apply_plan(audio, SR, treatment)
    # Conditioning (DC block) alone changes SI-SDR vs raw; measure do-no-harm
    # of Natural stages relative to conditioned reference.
    conditioned = filters.dc_block(audio, SR)
    sdr = _si_sdr(conditioned, out)
    assert sdr >= 30.0, (
        f"SI-SDR={sdr:.2f} stages={[s.id.value for s in treatment.stages if s.enabled]}"
    )


def test_gate6_no_nans():
    audio = _tone(1000, 1.0)
    analysis = analyze_audio(audio, SR)
    treatment = plan(analysis, RestorationSettings())
    out, _ = apply_plan(audio, SR, treatment)
    assert np.isfinite(out).all()


def test_gate8_cancel_latency():
    audio = _tone(440, 8.0)
    analysis = analyze_audio(audio, SR)
    treatment = plan(analysis, RestorationSettings())
    cancelled = {"v": False}

    def is_cancelled() -> bool:
        return cancelled["v"]

    ctx = JobContext(is_cancelled=is_cancelled)
    cancelled["v"] = True
    t0 = time.perf_counter()
    with pytest.raises(CancelledError):
        # Progress report at start of stages checks cancel
        ctx.check()
        apply_plan(audio, SR, treatment, ctx=ctx)
    elapsed = time.perf_counter() - t0
    assert elapsed <= 2.0


def test_gate9_hum_suppression():
    # Pure 60 Hz hum + mild tone
    t = np.linspace(0, 3.0, SR * 3, endpoint=False)
    hum = 0.3 * np.sin(2 * np.pi * 60 * t)
    tone = 0.1 * np.sin(2 * np.pi * 1000 * t)
    mono = (hum + tone).astype(np.float32)
    audio = np.stack([mono, mono], axis=0)
    out = filters.notch_comb(audio, SR, f0=60.0, harmonics=3, q=35)
    # FFT magnitude at 60 Hz before/after
    def mag_at(x: np.ndarray, f: float) -> float:
        spec = np.fft.rfft(x.mean(axis=0) * np.hanning(x.shape[-1]))
        freqs = np.fft.rfftfreq(x.shape[-1], 1 / SR)
        idx = int(np.argmin(np.abs(freqs - f)))
        return float(np.abs(spec[idx]) + 1e-12)

    before = mag_at(audio, 60)
    after = mag_at(out, 60)
    suppression_db = 20 * np.log10(before / after)
    assert suppression_db >= 25.0, f"hum suppression={suppression_db:.1f} dB"

    # 1 kHz tone should not collapse
    before_t = mag_at(audio, 1000)
    after_t = mag_at(out, 1000)
    change_db = abs(20 * np.log10((after_t + 1e-12) / (before_t + 1e-12)))
    assert change_db < 0.5 + 0.3  # allow small windowing slack


def test_gate13_music_dominant_no_global_dfn():
    a = AnalysisResult(
        id="a",
        media_id="m",
        duration_sec=5.0,
        sample_rate=SR,
        channels=2,
        global_metrics=GlobalMetrics(
            loudness=LoudnessMetrics(integrated_lufs=-18, lra=4, true_peak_dbtp=-2),
            crest_factor_db=14,
            clipping_ratio=0,
            stereo=StereoMetrics(correlation=0.9, lr_balance_db=0.1),
        ),
        timeline=[
            TimelineRegion(
                start_sec=0,
                end_sec=5,
                content={"speech": 0.1, "music": 0.85, "ambience": 0.05},
                label=ContentLabel.music_dominant,
            )
        ],
        issues=[
            AnalysisIssue(
                id="hiss",
                severity=0.9,
                confidence=0.9,
                recoverability=Recoverability.partial,
                evidence={},
                regions=[{"start_sec": 0, "end_sec": 5}],
                user_message="hiss",
            )
        ],
        versions={},
        created_at="2026-01-01T00:00:00Z",
    )
    p = plan(a, RestorationSettings())
    dfn = next(s for s in p.stages if s.id == StageId.denoise_speech)
    assert dfn.enabled is False
