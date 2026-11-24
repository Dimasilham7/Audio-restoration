"""Shared Pydantic schemas for analysis, plans, settings, and jobs."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Recoverability(str, Enum):
    recoverable = "recoverable"
    partial = "partial"
    not_recoverable = "not_recoverable"


class ContentLabel(str, Enum):
    speech_dominant = "speech_dominant"
    music_dominant = "music_dominant"
    mixed = "mixed"
    ambience = "ambience"


class Preset(str, Enum):
    natural = "natural"
    balanced = "balanced"
    enhanced = "enhanced"


class StageId(str, Enum):
    condition = "condition"
    declip = "declip"
    hum_notch = "hum_notch"
    wind_rumble = "wind_rumble"
    denoise_speech = "denoise_speech"
    denoise_music_gate = "denoise_music_gate"
    tonal_eq = "tonal_eq"
    stereo = "stereo"
    dynamics = "dynamics"
    deess = "deess"
    loudness = "loudness"
    limiter = "limiter"


class LoudnessMetrics(BaseModel):
    integrated_lufs: float
    lra: float = 0.0
    true_peak_dbtp: float
    momentary_max_lufs: float | None = None
    short_term_max_lufs: float | None = None


class StereoMetrics(BaseModel):
    correlation: float
    lr_balance_db: float
    polarity_inverted: bool = False


class GlobalMetrics(BaseModel):
    loudness: LoudnessMetrics
    crest_factor_db: float
    clipping_ratio: float
    stereo: StereoMetrics
    spectral: dict[str, float] = Field(default_factory=dict)


class TimelineRegion(BaseModel):
    start_sec: float
    end_sec: float
    content: dict[str, float]
    label: ContentLabel


class AnalysisIssue(BaseModel):
    id: str
    severity: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    recoverability: Recoverability
    evidence: dict[str, Any] = Field(default_factory=dict)
    regions: list[dict[str, float]] = Field(default_factory=list)
    user_message: str


class AnalysisResult(BaseModel):
    schema_version: str = "1.0.0"
    id: str
    media_id: str
    duration_sec: float
    sample_rate: int
    channels: int
    global_metrics: GlobalMetrics
    timeline: list[TimelineRegion] = Field(default_factory=list)
    issues: list[AnalysisIssue] = Field(default_factory=list)
    versions: dict[str, str] = Field(default_factory=dict)
    created_at: str


class PlannedStage(BaseModel):
    id: StageId
    enabled: bool
    reason: str
    confidence: float = Field(ge=0, le=1)
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[StageId] = Field(default_factory=list)
    conflicts_with: list[StageId] = Field(default_factory=list)


class TreatmentPlan(BaseModel):
    schema_version: str = "1.0.0"
    id: str
    analysis_id: str
    preset: Preset
    stages: list[PlannedStage]
    warnings: list[str] = Field(default_factory=list)
    created_at: str


class RestorationSettings(BaseModel):
    schema_version: str = "1.0.0"
    preset: Preset = Preset.balanced
    strength: float = Field(0.6, ge=0, le=1)
    music_enhancement: float = Field(0.5, ge=0, le=1)
    speech_clarity: float = Field(0.5, ge=0, le=1)
    ambience_preservation: float = Field(0.6, ge=0, le=1)
    noise_reduction: float = Field(0.5, ge=0, le=1)
    bass_balance: float = Field(0.0, ge=-1, le=1)
    treble_recovery: float = Field(0.5, ge=0, le=1)
    stereo_width: float = Field(1.0, ge=0.5, le=1.5)
    loudness_target_lufs: float = -16.0
    module_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    model_versions: dict[str, str] = Field(default_factory=dict)


class ProcessReport(BaseModel):
    analysis: AnalysisResult
    plan: TreatmentPlan
    settings: RestorationSettings
    input_path: str
    output_audio_path: str
    output_media_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    sample_count_ok: bool
    stages_applied: list[str] = Field(default_factory=list)
