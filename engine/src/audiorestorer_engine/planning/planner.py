"""Rule-based treatment planner (pure function)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from audiorestorer_engine.schemas import (
    AnalysisResult,
    ContentLabel,
    PlannedStage,
    Preset,
    RestorationSettings,
    StageId,
    TreatmentPlan,
)

_PRESET_STRENGTH = {
    Preset.natural: 0.35,
    Preset.balanced: 0.6,
    Preset.enhanced: 0.85,
}


def plan(
    analysis: AnalysisResult,
    settings: RestorationSettings | None = None,
) -> TreatmentPlan:
    settings = settings or RestorationSettings()
    preset = settings.preset
    strength = settings.strength if settings.strength else _PRESET_STRENGTH[preset]
    issues = {i.id: i for i in analysis.issues}
    label = (
        analysis.timeline[0].label if analysis.timeline else ContentLabel.mixed
    )

    stages: list[PlannedStage] = []
    warnings: list[str] = []

    stages.append(
        PlannedStage(
            id=StageId.condition,
            enabled=True,
            reason="DC block and conditioning",
            confidence=1.0,
            params={},
        )
    )

    clip = issues.get("clipping")
    stages.append(
        PlannedStage(
            id=StageId.declip,
            enabled=bool(clip and clip.confidence >= 0.6),
            reason=clip.user_message if clip else "No significant clipping",
            confidence=clip.confidence if clip else 0.0,
            params={"threshold": 0.99},
        )
    )

    hum = issues.get("hum")
    stages.append(
        PlannedStage(
            id=StageId.hum_notch,
            enabled=bool(hum and hum.confidence >= 0.55),
            reason=hum.user_message if hum else "No hum detected",
            confidence=hum.confidence if hum else 0.0,
            params={
                "f0_hz": (hum.evidence.get("f0_hz") if hum else 50),
                "harmonics": 5 if preset != Preset.enhanced else 7,
                "q": 35.0,
            },
        )
    )

    wind = issues.get("wind")
    wind_cut = 80.0 + 40.0 * strength
    if label == ContentLabel.music_dominant:
        wind_cut = min(wind_cut, 60.0)
        if wind and wind.confidence >= 0.55:
            warnings.append("Wind HPF limited to protect music bass.")
    stages.append(
        PlannedStage(
            id=StageId.wind_rumble,
            enabled=bool(wind and wind.confidence >= 0.55),
            reason=wind.user_message if wind else "No wind/rumble",
            confidence=wind.confidence if wind else 0.0,
            params={"cutoff_hz": wind_cut},
        )
    )

    hiss = issues.get("hiss")
    noise_issue = hiss or wind or issues.get("background_noise")

    # Attenuation limits by preset (plan doc); ambience preservation lowers strength
    atten_by_preset = {
        Preset.natural: 6.0,
        Preset.balanced: 12.0,
        Preset.enhanced: 18.0,
    }
    atten = atten_by_preset[preset] * (0.55 + 0.45 * settings.noise_reduction)
    atten *= 1.0 - 0.4 * settings.ambience_preservation
    atten = float(max(0.0, min(24.0, atten)))
    # speech clarity pushes a bit more reduction on speech content
    if label == ContentLabel.speech_dominant:
        atten = min(24.0, atten + 3.0 * settings.speech_clarity * strength)

    speech_p = 0.0
    if analysis.timeline:
        speech_p = float(analysis.timeline[0].content.get("speech", 0.0))

    speech_denoise = False
    speech_reason = "Speech denoise not indicated"
    speech_conf = 0.0
    use_vad_gate = label == ContentLabel.mixed

    if label == ContentLabel.music_dominant and speech_p < 0.22:
        speech_reason = "Blocked: music-dominant - never apply speech enhancer to music"
        speech_conf = 0.9
    elif label == ContentLabel.music_dominant and speech_p >= 0.22 and noise_issue:
        # Phone concert / live: some speech under music - only via VAD gate
        speech_denoise = True
        use_vad_gate = True
        speech_conf = float(noise_issue.confidence) * 0.8
        speech_reason = (
            f"Gated DeepFilterNet3 (speech~{speech_p:.2f} under music; atten<={atten:.0f} dB)"
        )
    elif label in (ContentLabel.speech_dominant, ContentLabel.mixed):
        if noise_issue and noise_issue.confidence >= 0.45:
            speech_denoise = True
            speech_conf = float(noise_issue.confidence)
            speech_reason = (
                f"DeepFilterNet3 on speech regions (atten<={atten:.0f} dB); "
                f"gated for mixed content"
            )
        elif label == ContentLabel.speech_dominant and settings.noise_reduction >= 0.35:
            speech_denoise = True
            speech_conf = 0.55
            speech_reason = f"Speech-dominant with NR request (atten<={atten:.0f} dB)"
        use_vad_gate = label == ContentLabel.mixed or use_vad_gate

    # Import deferred availability check only for reason text
    try:
        from audiorestorer_engine.adapters.deepfilternet import is_available as dfn_available

        dfn_ok = dfn_available()
    except Exception:
        dfn_ok = False
    if speech_denoise and not dfn_ok:
        speech_denoise = False
        speech_reason = "DeepFilterNet CLI not installed (.models/deepfilternet)"
        warnings.append(speech_reason)

    stages.append(
        PlannedStage(
            id=StageId.denoise_speech,
            enabled=speech_denoise,
            reason=speech_reason,
            confidence=speech_conf,
            params={
                "atten_lim_db": atten,
                "gate_with_vad": use_vad_gate,
                "compensate_delay": True,
            },
        )
    )

    gate_on = bool(
        hiss
        and hiss.confidence >= 0.55
        and label in (ContentLabel.music_dominant, ContentLabel.mixed, ContentLabel.ambience)
        and not speech_denoise  # avoid stacking aggressive NR
    )
    stages.append(
        PlannedStage(
            id=StageId.denoise_music_gate,
            enabled=gate_on,
            reason="Gentle high-shelf cut on noise floor" if gate_on else "No music hiss gate",
            confidence=hiss.confidence if hiss else 0.0,
            params={"reduction_db": -3.0 - 6.0 * settings.noise_reduction * strength},
        )
    )

    muffled = issues.get("muffled")
    treble_gain = 0.0
    if muffled and muffled.confidence >= 0.45:
        treble_gain = min(9.0, (4.0 + 6.0 * settings.treble_recovery) * strength)
        # Cap by ambience preservation (less boost if preserving ambience noise)
        treble_gain *= 1.0 - 0.35 * settings.ambience_preservation
    if label == ContentLabel.speech_dominant:
        treble_gain *= 0.7 + 0.3 * settings.speech_clarity

    stages.append(
        PlannedStage(
            id=StageId.tonal_eq,
            enabled=treble_gain >= 0.5 or abs(settings.bass_balance) > 0.05,
            reason="Tonal correction for muffling / balance",
            confidence=muffled.confidence if muffled else 0.4,
            params={
                "high_shelf_hz": 3500.0,
                "high_shelf_db": treble_gain,
                "bass_hz": 120.0,
                "bass_db": float(settings.bass_balance) * 4.0 * strength,
            },
        )
    )

    imbalance = issues.get("stereo_imbalance")
    stages.append(
        PlannedStage(
            id=StageId.stereo,
            enabled=bool(imbalance and imbalance.confidence >= 0.55)
            or abs(settings.stereo_width - 1.0) > 0.05,
            reason="Stereo correction / width",
            confidence=imbalance.confidence if imbalance else 0.5,
            params={
                "lr_balance_db": (
                    imbalance.evidence.get("lr_balance_db", 0.0) if imbalance else 0.0
                ),
                "width": settings.stereo_width,
            },
        )
    )

    stages.append(
        PlannedStage(
            id=StageId.dynamics,
            enabled=preset == Preset.enhanced,
            reason="Light dynamics only in Enhanced preset",
            confidence=0.4,
            params={},
        )
    )

    stages.append(
        PlannedStage(
            id=StageId.deess,
            enabled=False,
            reason="De-esser deferred until speech gating adapter lands",
            confidence=0.0,
            params={},
        )
    )

    stages.append(
        PlannedStage(
            id=StageId.loudness,
            enabled=True,
            reason=f"Normalize toward {settings.loudness_target_lufs:.1f} LUFS",
            confidence=1.0,
            params={"target_lufs": settings.loudness_target_lufs},
        )
    )

    stages.append(
        PlannedStage(
            id=StageId.limiter,
            enabled=True,
            reason="True-peak ceiling -1 dBTP",
            confidence=1.0,
            params={"ceiling_dbtp": -1.0},
            depends_on=[StageId.loudness],
        )
    )

    # Apply module overrides last
    for stage in stages:
        override = settings.module_overrides.get(stage.id.value)
        if not override:
            continue
        if "enabled" in override:
            stage.enabled = bool(override["enabled"])
        if "params" in override and isinstance(override["params"], dict):
            stage.params.update(override["params"])

    return TreatmentPlan(
        id=str(uuid.uuid4()),
        analysis_id=analysis.id,
        preset=preset,
        stages=stages,
        warnings=warnings,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
