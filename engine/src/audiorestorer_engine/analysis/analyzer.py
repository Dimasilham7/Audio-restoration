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

    # Overlapping STFT for stabler spectral stats (phone AAC / short clips)
    hop = 512
    n_fft = 2048
    S, _ = stft_magnitude(mono, n_fft=n_fft, hop_length=hop)
    freqs = fft_freqs(sample_rate, n_fft=n_fft)
    power = np.maximum(S.astype(np.float64) ** 2, 1e-20)
    power_sum = float(np.sum(power) + 1e-12)
    centroid = float(np.sum(freqs[:, None] * power) / power_sum)
    flatness = float(
        np.exp(np.mean(np.log(power))) / (np.mean(power) + 1e-12)
    )

    mid = np.logical_and(freqs >= 500, freqs < 2000)
    presence = np.logical_and(freqs >= 2000, freqs < 5000)
    high = np.logical_and(freqs >= 4000, freqs < min(16000.0, sample_rate * 0.45))
    very_high = freqs >= min(8000.0, sample_rate * 0.45 - 1)
    mid_e = float(np.mean(power[mid, :]) + 1e-20)
    presence_e = float(np.mean(power[presence, :]) + 1e-20)
    high_e = float(np.mean(power[high, :]) + 1e-20)
    vh_e = float(np.mean(power[very_high, :]) + 1e-20) if np.any(very_high) else high_e
    # Phone AAC bass music can have 4k+/mid ≈ 0; use 2–5 kHz "presence" as primary tilt cue
    hf_ratio = high_e / mid_e
    presence_ratio = presence_e / mid_e
    brightness = vh_e / (presence_e + 1e-20)

    # Spectral flux (frame-to-frame) for content cues
    log_power = np.log(power + 1e-12)
    if power.shape[1] > 1:
        flux = float(np.mean(np.maximum(0.0, np.diff(log_power, axis=1))))
        flux_std = float(np.std(np.sum(np.maximum(0.0, np.diff(power, axis=1)), axis=0)))
    else:
        flux = 0.0
        flux_std = 0.0

    avg_mag = np.mean(S, axis=1)
    hum_f0, hum_score = _detect_hum(avg_mag, freqs)

    rms_frames = frame_rms(mono, frame=n_fft, hop=hop)
    # Align quiet mask to STFT frames
    n_frames = power.shape[1]
    if rms_frames.size != n_frames:
        # resample rms frames roughly
        idx = np.linspace(0, max(rms_frames.size - 1, 0), n_frames)
        rms_frames = np.interp(idx, np.arange(rms_frames.size), rms_frames)

    quiet = rms_frames <= np.percentile(rms_frames, 25)
    active = rms_frames >= np.percentile(rms_frames, 50)
    if np.any(quiet) and np.any(active):
        quiet_high = float(np.mean(power[high][:, quiet]) + 1e-20)
        active_high = float(np.mean(power[high][:, active]) + 1e-20)
        quiet_vs_active = quiet_high / (active_high + 1e-20)
        # Hiss only when quiet HF floor is both audible and close to active HF
        # (constant noise bed). Dynamic music with quiet gaps (qva≪1) is not hiss.
        mid_quiet = float(np.mean(power[mid][:, quiet]) + 1e-20)
        floor_vs_mid = quiet_high / mid_quiet
        if quiet_vs_active >= 0.45 and floor_vs_mid >= 0.0008:
            hiss_score = float(
                np.clip(
                    0.35 * ((quiet_vs_active - 0.45) / 0.55)
                    + 0.45 * np.clip(np.log10(quiet_high * 1e5 + 1e-6) / 3.0, 0, 1)
                    + 0.2 * np.clip(floor_vs_mid / 0.01, 0, 1),
                    0,
                    1,
                )
            )
        elif quiet_vs_active >= 0.7 and quiet_high > 1e-2:
            hiss_score = float(np.clip(0.55 + 0.4 * (quiet_vs_active - 0.7) / 0.3, 0, 1))
        else:
            hiss_score = 0.0
    else:
        quiet_vs_active = 0.0
        hiss_score = 0.0

    low = freqs < 120
    low_frames = np.mean(power[low, :], axis=0)
    wind_score = float(
        np.clip((np.std(low_frames) / (np.mean(low_frames) + 1e-12)) / 2.5, 0, 1)
    )

    # Muffled via presence band (2–5 kHz). Phone music often ~0.02–0.06;
    # only severe suppression scores high so severity varies across clips.
    if presence_ratio < 0.02:
        muffled_score = float(np.clip(0.55 + (0.02 - presence_ratio) / 0.02 * 0.45, 0.55, 1.0))
    elif presence_ratio < 0.045:
        muffled_score = float(np.clip((0.045 - presence_ratio) / 0.045, 0.25, 0.7))
    elif presence_ratio < 0.09:
        muffled_score = float(np.clip((0.09 - presence_ratio) / 0.09 * 0.4, 0, 0.4))
    else:
        muffled_score = 0.0

    zcr = zero_crossing_rate(mono, frame=n_fft, hop=hop)
    zcr_frames = _zcr_frames(mono, frame=n_fft, hop=hop)
    zcr_std = float(np.std(zcr_frames)) if zcr_frames.size > 1 else 0.0

    speech_p, music_p, amb_p, label = _content_probs(
        zcr=zcr,
        zcr_std=zcr_std,
        crest=crest,
        centroid=centroid,
        flatness=flatness,
        flux=flux,
        flux_std=flux_std,
        sample_rate=sample_rate,
    )

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

    if hum_score >= 0.45:
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

    # Higher bar for hiss to avoid same card on every phone clip
    if hiss_score >= 0.58:
        issues.append(
            AnalysisIssue(
                id="hiss",
                severity=float(hiss_score),
                confidence=float(0.4 + 0.45 * hiss_score),
                recoverability=Recoverability.partial,
                evidence={
                    "score": hiss_score,
                    "quiet_vs_active_hf": quiet_vs_active,
                    "hf_ratio": hf_ratio,
                },
                regions=full_region,
                user_message="High-frequency hiss / noise floor elevated in quiet sections.",
            )
        )

    if wind_score >= 0.55 and label != ContentLabel.music_dominant:
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
                confidence=float(0.45 + 0.4 * muffled_score),
                recoverability=Recoverability.partial,
                evidence={
                    "hf_ratio": hf_ratio,
                    "presence_ratio": presence_ratio,
                    "brightness": brightness,
                    "centroid_hz": centroid,
                },
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
                "presence_ratio": float(presence_ratio),
                "brightness": float(brightness),
                "flux": float(flux),
            },
        ),
        timeline=timeline,
        issues=issues,
        versions={"analyzer": __version__, "engine": __version__},
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _zcr_frames(mono: np.ndarray, *, frame: int, hop: int) -> np.ndarray:
    if mono.size < 2:
        return np.zeros(1, dtype=np.float32)
    if mono.size < frame:
        return np.array(
            [float(np.mean(np.abs(np.diff(np.signbit(mono).astype(np.int8)))))],
            dtype=np.float32,
        )
    n_frames = 1 + max(0, (mono.size - frame) // hop)
    rates = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        chunk = mono[i * hop : i * hop + frame]
        rates[i] = float(np.mean(np.abs(np.diff(np.signbit(chunk).astype(np.int8)))))
    return rates


def _content_probs(
    *,
    zcr: float,
    zcr_std: float,
    crest: float,
    centroid: float,
    flatness: float,
    flux: float,
    flux_std: float,
    sample_rate: int,
) -> tuple[float, float, float, ContentLabel]:
    """Richer speech/music/ambience heuristic (not forced to sum via 1-speech)."""
    # Normalize cues
    zcr_s = float(np.clip((zcr - 0.04) / 0.12, 0, 1))
    zcr_var_s = float(np.clip(zcr_std / 0.08, 0, 1))
    crest_s = float(np.clip((crest - 8.0) / 12.0, 0, 1))
    cent_s = float(np.clip(centroid / (sample_rate * 0.25), 0, 1))
    flat_s = float(np.clip(flatness * 8.0, 0, 1))
    flux_s = float(np.clip(flux * 20.0, 0, 1))

    # Speech: mid ZCR, variable ZCR, moderate crest, mid centroid
    speech = 0.25 + 0.35 * zcr_s + 0.25 * zcr_var_s + 0.15 * (1.0 - abs(crest_s - 0.35))
    speech += 0.1 * (1.0 - abs(cent_s - 0.35))
    speech -= 0.15 * flat_s

    # Music: lower/steadier ZCR, more tonal (low flatness), often higher crest or flux structure
    music = 0.2 + 0.35 * (1.0 - zcr_s) + 0.2 * (1.0 - flat_s) + 0.15 * crest_s
    music += 0.15 * flux_s - 0.1 * zcr_var_s

    # Ambience: flatter spectrum, lower crest, steadier energy
    amb = 0.15 + 0.4 * flat_s + 0.25 * (1.0 - crest_s) + 0.15 * (1.0 - flux_s)

    # Softmax-ish normalize
    raw = np.array([max(0.01, speech), max(0.01, music), max(0.01, amb)], dtype=np.float64)
    probs = raw / raw.sum()
    speech_p, music_p, amb_p = float(probs[0]), float(probs[1]), float(probs[2])
    label = _label(speech_p, music_p, amb_p)
    return speech_p, music_p, amb_p, label


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
    # Require clearer margin so mixed/ambience can appear
    if speech_p >= 0.42 and speech_p >= music_p + 0.05:
        return ContentLabel.speech_dominant
    if music_p >= 0.45 and music_p >= speech_p + 0.08:
        return ContentLabel.music_dominant
    if amb_p >= 0.4 and amb_p >= speech_p and amb_p >= music_p:
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
