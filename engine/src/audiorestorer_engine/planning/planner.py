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
    Preset.natural: 0.4,
    Preset.balanced: 0.7,
    Preset.enhanced: 0.95,
}


def plan(
    analysis: AnalysisResult,
    settings: RestorationSettings | None = None,
) -> TreatmentPlan:
    settings = settings or RestorationSettings()
    preset = settings.preset
    strength = settings.strength if settings.strength else _PRESET_STRENGTH[preset]
    # Preset pushes effective strength so Enhanced is clearly more audible
    preset_boost = {Preset.natural: 0.85, Preset.balanced: 1.05, Preset.enhanced: 1.25}[preset]
    strength = float(min(1.0, strength * preset_boost))

    issues = {i.id: i for i in analysis.issues}
    label = analysis.timeline[0].label if analysis.timeline else ContentLabel.mixed
    speech_p = float(analysis.timeline[0].content.get("speech", 0.0)) if analysis.timeline else 0.0
    music_p = float(analysis.timeline[0].content.get("music", 0.0)) if analysis.timeline else 0.0
    hf_ratio = float(analysis.global_metrics.spectral.get("hf_ratio", 0.2))
    lufs = float(analysis.global_metrics.loudness.integrated_lufs)

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
    wind_cut = 70.0 + 50.0 * strength
    if label == ContentLabel.music_dominant:
        wind_cut = min(wind_cut, 55.0)
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

    atten_by_preset = {
        Preset.natural: 8.0,
        Preset.balanced: 14.0,
        Preset.enhanced: 20.0,
    }
    atten = atten_by_preset[preset] * (0.5 + 0.5 * settings.noise_reduction)
    atten *= 1.0 - 0.35 * settings.ambience_preservation
    if noise_issue:
        atten *= 0.75 + 0.5 * float(noise_issue.severity)
    atten = float(max(0.0, min(24.0, atten)))
    if label == ContentLabel.speech_dominant:
        atten = min(24.0, atten + 4.0 * settings.speech_clarity * strength)

    speech_denoise = False
    speech_reason = "Speech denoise not indicated"
    speech_conf = 0.0
    use_vad_gate = label in (ContentLabel.mixed, ContentLabel.music_dominant)

    if label == ContentLabel.music_dominant and speech_p < 0.32:
        speech_reason = "Blocked: music-dominant - never apply speech enhancer to music"
        speech_conf = 0.9
    elif label == ContentLabel.music_dominant and speech_p >= 0.32 and noise_issue:
        speech_denoise = True
        use_vad_gate = True
        speech_conf = float(noise_issue.confidence) * 0.8
        speech_reason = (
            f"Gated DeepFilterNet3 (speech~{speech_p:.2f} under music; atten<={atten:.0f} dB)"
        )
    elif label in (ContentLabel.speech_dominant, ContentLabel.mixed):
        if noise_issue and noise_issue.confidence >= 0.5:
            speech_denoise = True
            speech_conf = float(noise_issue.confidence)
            speech_reason = (
                f"DeepFilterNet3 on speech regions (atten<={atten:.0f} dB); "
                f"{'VAD-gated' if use_vad_gate else 'full'}"
            )
        elif label == ContentLabel.speech_dominant and settings.noise_reduction >= 0.3:
            speech_denoise = True
            speech_conf = 0.55
            speech_reason = f"Speech-dominant with NR request (atten<={atten:.0f} dB)"
        use_vad_gate = label != ContentLabel.speech_dominant or use_vad_gate

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

    # Music gate: stronger when hissy music and DFN not used
    gate_on = bool(
        hiss
        and hiss.confidence >= 0.55
        and label in (ContentLabel.music_dominant, ContentLabel.mixed, ContentLabel.ambience)
        and not speech_denoise
    )
    gate_db = -4.0 - 8.0 * settings.noise_reduction * strength
    if gate_on and preset == Preset.enhanced:
        gate_db -= 2.0
    stages.append(
        PlannedStage(
            id=StageId.denoise_music_gate,
            enabled=gate_on,
            reason=(
                f"High-shelf noise-floor cut ({gate_db:.1f} dB)"
                if gate_on
                else "No music hiss gate"
            ),
            confidence=hiss.confidence if hiss else 0.0,
            params={"reduction_db": gate_db},
        )
    )

    muffled = issues.get("muffled")
    presence_ratio = float(analysis.global_metrics.spectral.get("presence_ratio", 0.1))
    treble_gain = 0.0
    if muffled and muffled.confidence >= 0.4:
        # Audible recovery scaled by severity (presence-based)
        depth = float(muffled.severity)
        treble_gain = (4.0 + 8.0 * settings.treble_recovery) * strength * (0.45 + 0.55 * depth)
        treble_gain *= 1.0 - 0.25 * settings.ambience_preservation
        if preset == Preset.enhanced:
            treble_gain *= 1.25
        # Extra lift when presence band is especially thin
        if presence_ratio < 0.025:
            treble_gain *= 1.15
        treble_gain = float(min(11.0, treble_gain))
    elif label == ContentLabel.speech_dominant and settings.speech_clarity >= 0.55:
        treble_gain = 2.5 * settings.speech_clarity * strength
    elif (
        label == ContentLabel.music_dominant
        and settings.music_enhancement >= 0.55
        and presence_ratio < 0.05
        and preset != Preset.natural
    ):
        # Mild air for dull music beds even without a hard muffled flag
        treble_gain = 2.0 * settings.music_enhancement * strength
    if label == ContentLabel.speech_dominant:
        treble_gain *= 0.75 + 0.35 * settings.speech_clarity

    bass_db = float(settings.bass_balance) * 5.0 * strength
    if label == ContentLabel.music_dominant and settings.music_enhancement >= 0.45:
        # Mild musical body when user asks for music enhancement
        bass_db += 1.5 * settings.music_enhancement * strength
        if preset == Preset.enhanced:
            bass_db += 1.0 * settings.music_enhancement

    tonal_on = abs(treble_gain) >= 0.6 or abs(bass_db) >= 0.6
    stages.append(
        PlannedStage(
            id=StageId.tonal_eq,
            enabled=tonal_on,
            reason=(
                f"Tonal EQ (treble {treble_gain:+.1f} dB, bass {bass_db:+.1f} dB)"
                if tonal_on
                else "No tonal correction needed"
            ),
            confidence=muffled.confidence if muffled else 0.35,
            params={
                "high_shelf_hz": 3200.0 if label == ContentLabel.speech_dominant else 3500.0,
                "high_shelf_db": treble_gain,
                "bass_hz": 120.0,
                "bass_db": bass_db,
            },
        )
    )

    imbalance = issues.get("stereo_imbalance")
    width = settings.stereo_width
    if label == ContentLabel.music_dominant and settings.music_enhancement >= 0.6 and abs(width - 1.0) < 0.02:
        width = 1.0 + 0.12 * settings.music_enhancement * strength
    stages.append(
        PlannedStage(
            id=StageId.stereo,
            enabled=bool(imbalance and imbalance.confidence >= 0.55) or abs(width - 1.0) > 0.04,
            reason="Stereo correction / width",
            confidence=imbalance.confidence if imbalance else 0.45,
            params={
                "lr_balance_db": (
                    imbalance.evidence.get("lr_balance_db", 0.0) if imbalance else 0.0
                ),
                "width": width,
            },
        )
    )

    stages.append(
        PlannedStage(
            id=StageId.dynamics,
            enabled=preset == Preset.enhanced and label != ContentLabel.ambience,
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

    # Loudness: skip if already very close (keeps A/B more about tone/noise)
    loud_err = abs(lufs - settings.loudness_target_lufs) if lufs > -70 else 99.0
    loud_on = loud_err >= 1.25 or preset == Preset.enhanced
    if not loud_on:
        warnings.append(
            f"Loudness already near target ({lufs:.1f} vs {settings.loudness_target_lufs:.1f} LUFS); skipped."
        )
    stages.append(
        PlannedStage(
            id=StageId.loudness,
            enabled=loud_on,
            reason=(
                f"Normalize toward {settings.loudness_target_lufs:.1f} LUFS"
                if loud_on
                else "Loudness already near target"
            ),
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

    # Content-specific tip
    if label == ContentLabel.music_dominant and speech_denoise:
        warnings.append("Speech enhancer is VAD-gated so music beds stay protected.")
    if label == ContentLabel.music_dominant and not speech_denoise and not gate_on and not tonal_on:
        warnings.append("Clean-ish music bed: only light conditioning/limiting applied.")
    if hf_ratio < 0.1 and muffled:
        warnings.append("Phone/AAC may lack HF permanently; EQ cannot invent missing detail.")

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
