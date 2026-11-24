"""Multi-label analyzer using numpy/scipy only (no librosa)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import numpy as np

from audiorestorer_engine import __version__
from audiorestorer_engine.analysis.spectral import (
    fft_freqs,
    frame_rms,
    stft_magnitude,
    zero_crossing_rate,
)
from audiorestorer_engine.dsp.loudness import measure_loudness
from audiorestorer_engine.schemas import (
    AnalysisIssue,
    AnalysisResult,
    ContentLabel,
    GlobalMetrics,
    LoudnessMetrics,
    Recoverability,
    StereoMetrics,
    TimelineRegion,
)


def analyze_audio(
    audio: np.ndarray,
    sample_rate: int,
    *,
    media_id: str = "local",
) -> AnalysisResult:
    """Analyze float32 audio shaped (channels, samples)."""
    n_samples = audio.shape[-1]
    duration = n_samples / float(sample_rate)
    mono = np.mean(audio, axis=0) if audio.shape[0] > 1 else audio[0]

    loud = measure_loudness(audio, sample_rate)
    peak = float(np.max(np.abs(audio)) + 1e-12)
    rms = float(np.sqrt(np.mean(mono**2)) + 1e-12)
    crest = 20.0 * np.log10(peak / rms)

    clip_thresh = 0.99
    clipping_ratio = float(np.mean(np.abs(mono) >= clip_thresh))

    hop = 2048
    n_fft = 2048
    S, _ = stft_magnitude(mono, n_fft=n_fft, hop_length=hop)
    freqs = fft_freqs(sample_rate, n_fft=n_fft)
    power = S**2
    power_sum = np.sum(power) + 1e-12
    centroid = float(np.sum(freqs[:, None] * power) / power_sum)
    flatness = float(np.exp(np.mean(np.log(power + 1e-12))) / (np.mean(power) + 1e-12))
    mid = np.logical_and(freqs >= 500, freqs < 2000)
    high = freqs >= 4000
    mid_e = float(np.mean(power[mid, :]) + 1e-12)
    high_e = float(np.mean(power[high, :]) + 1e-12)
    hf_ratio = high_e / mid_e

    avg_mag = np.mean(S, axis=1)
    hum_f0, hum_score = _detect_hum(avg_mag, freqs)

    rms_frames = frame_rms(mono, frame=n_fft, hop=hop)
    quiet = rms_frames <= np.percentile(rms_frames, 20)
    if np.any(quiet) and power.shape[1] == quiet.shape[0]:
        quiet_high = float(np.mean(power[high][:, quiet]) + 1e-12)
        hiss_score = float(np.clip(np.log10(quiet_high * 1e6 + 1e-6) / 3.0, 0, 1))
    else:
        hiss_score = 0.0

    low = freqs < 120
    low_frames = np.mean(power[low, :], axis=0)
    wind_score = float(np.clip((np.std(low_frames) / (np.mean(low_frames) + 1e-12)) / 2.0, 0, 1))

    muffled_score = float(np.clip((0.35 - hf_ratio) / 0.35, 0, 1)) if hf_ratio < 0.35 else 0.0

    zcr = zero_crossing_rate(mono, frame=n_fft, hop=hop)
    speech_p = float(np.clip(0.35 + (zcr - 0.05) * 4.0 - max(0, crest - 14) * 0.03, 0, 1))
    music_p = float(np.clip(1.0 - speech_p - 0.1, 0, 1))
    amb_p = float(max(0.0, 1.0 - speech_p - music_p))
    label = _label(speech_p, music_p, amb_p)

    stereo = _stereo_metrics(audio)

    issues: list[AnalysisIssue] = []
    full_region = [{"start_sec": 0.0, "end_sec": duration}]

    if clipping_ratio > 0.001:
        issues.append(
            AnalysisIssue(
                id="clipping",
                severity=float(np.clip(clipping_ratio * 20, 0, 1)),
                confidence=0.85 if clipping_ratio > 0.01 else 0.6,
                recoverability=Recoverability.partial,
                evidence={"clipping_ratio": clipping_ratio},
                regions=full_region,
                user_message=(
                    f"Clipping detected in ~{clipping_ratio * 100:.2f}% of samples. "
                    "Repair is partial."
                ),
            )
        )

    if hum_score >= 0.4:
        issues.append(
            AnalysisIssue(
                id="hum",
                severity=float(hum_score),
                confidence=float(0.5 + 0.4 * hum_score),
                recoverability=Recoverability.recoverable,
                evidence={"f0_hz": hum_f0, "score": hum_score},
                regions=full_region,
                user_message=f"Electrical hum around {hum_f0:.0f} Hz detected.",
            )
        )

    if hiss_score >= 0.45:
        issues.append(
            AnalysisIssue(
                id="hiss",
                severity=float(hiss_score),
                confidence=float(0.45 + 0.4 * hiss_score),
                recoverability=Recoverability.partial,
                evidence={"score": hiss_score},
                regions=full_region,
                user_message="High-frequency hiss / noise floor elevated in quiet sections.",
            )
        )

    if wind_score >= 0.5 and label != ContentLabel.music_dominant:
        issues.append(
            AnalysisIssue(
                id="wind",
                severity=float(wind_score),
                confidence=0.55,
                recoverability=Recoverability.partial,
                evidence={"score": wind_score},
                regions=full_region,
                user_message="Low-frequency rumble / possible wind noise.",
            )
        )

    if muffled_score >= 0.4:
        issues.append(
            AnalysisIssue(
                id="muffled",
                severity=float(muffled_score),
                confidence=0.55,
                recoverability=Recoverability.partial,
                evidence={"hf_ratio": hf_ratio, "centroid_hz": centroid},
                regions=full_region,
                user_message=(
                    "High frequencies look suppressed (muffled). "
                    "EQ can help where signal remains; it will not invent missing detail."
                ),
            )
        )

    if abs(stereo.lr_balance_db) >= 2.5 and audio.shape[0] > 1:
        issues.append(
            AnalysisIssue(
                id="stereo_imbalance",
                severity=float(np.clip(abs(stereo.lr_balance_db) / 8.0, 0, 1)),
                confidence=0.7,
                recoverability=Recoverability.recoverable,
                evidence={"lr_balance_db": stereo.lr_balance_db},
                regions=full_region,
                user_message=f"Stereo imbalance ~{stereo.lr_balance_db:.1f} dB (L-R).",
            )
        )

    if loud["integrated_lufs"] < -28 or loud["integrated_lufs"] > -12:
        issues.append(
            AnalysisIssue(
                id="loudness",
                severity=0.5,
                confidence=0.8,
                recoverability=Recoverability.recoverable,
                evidence={"integrated_lufs": loud["integrated_lufs"]},
                regions=full_region,
                user_message=f"Loudness is {loud['integrated_lufs']:.1f} LUFS (outside typical targets).",
            )
        )

    timeline = [
        TimelineRegion(
            start_sec=0.0,
            end_sec=duration,
            content={"speech": speech_p, "music": music_p, "ambience": amb_p},
            label=label,
        )
    ]

    return AnalysisResult(
        id=str(uuid.uuid4()),
        media_id=media_id,
        duration_sec=duration,
        sample_rate=sample_rate,
        channels=int(audio.shape[0]),
        global_metrics=GlobalMetrics(
            loudness=LoudnessMetrics(
                integrated_lufs=loud["integrated_lufs"],
                lra=loud["lra"],
                true_peak_dbtp=loud["true_peak_dbtp"],
            ),
            crest_factor_db=float(crest),
            clipping_ratio=clipping_ratio,
            stereo=stereo,
            spectral={
                "centroid_hz": centroid,
                "flatness": flatness,
                "hf_ratio": float(hf_ratio),
            },
        ),
        timeline=timeline,
        issues=issues,
        versions={"analyzer": __version__, "engine": __version__},
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _detect_hum(avg_mag: np.ndarray, freqs: np.ndarray) -> tuple[float, float]:
    best_f0 = 50.0
    best_score = 0.0
    for f0 in (50.0, 60.0):
        score = 0.0
        for n in range(1, 6):
            target = f0 * n
            if target >= freqs[-1]:
                break
            bin_idx = int(np.argmin(np.abs(freqs - target)))
            neigh = avg_mag[max(0, bin_idx - 10) : bin_idx + 11]
            if neigh.size == 0:
                continue
            score += float(avg_mag[bin_idx] / (np.median(neigh) + 1e-12))
        score /= 5.0
        norm = float(np.clip((score - 1.2) / 3.0, 0, 1))
        if norm > best_score:
            best_score = norm
            best_f0 = f0
    return best_f0, best_score


def _label(speech_p: float, music_p: float, amb_p: float) -> ContentLabel:
    if speech_p >= 0.55 and speech_p >= music_p:
        return ContentLabel.speech_dominant
    if music_p >= 0.55 and music_p > speech_p:
        return ContentLabel.music_dominant
    if amb_p >= 0.5:
        return ContentLabel.ambience
    return ContentLabel.mixed


def _stereo_metrics(audio: np.ndarray) -> StereoMetrics:
    if audio.shape[0] < 2:
        return StereoMetrics(correlation=1.0, lr_balance_db=0.0, polarity_inverted=False)
    left, right = audio[0], audio[1]
    corr = float(np.corrcoef(left, right)[0, 1]) if left.size > 8 else 1.0
    if not np.isfinite(corr):
        corr = 0.0
    l_rms = float(np.sqrt(np.mean(left**2)) + 1e-12)
    r_rms = float(np.sqrt(np.mean(right**2)) + 1e-12)
    balance = 20.0 * np.log10(l_rms / r_rms)
    polarity = corr < -0.5
    return StereoMetrics(
        correlation=float(corr),
        lr_balance_db=float(balance),
        polarity_inverted=bool(polarity),
    )
