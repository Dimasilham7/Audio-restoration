from audiorestorer_engine.planning.planner import plan
from audiorestorer_engine.schemas import (
    AnalysisIssue,
    AnalysisResult,
    ContentLabel,
    GlobalMetrics,
    LoudnessMetrics,
    Recoverability,
    RestorationSettings,
    StereoMetrics,
    TimelineRegion,
)


def _analysis_with_hum() -> AnalysisResult:
    return AnalysisResult(
        id="a1",
        media_id="m1",
        duration_sec=10.0,
        sample_rate=48000,
        channels=2,
        global_metrics=GlobalMetrics(
            loudness=LoudnessMetrics(integrated_lufs=-22.0, lra=5.0, true_peak_dbtp=-1.5),
            crest_factor_db=12.0,
            clipping_ratio=0.0,
            stereo=StereoMetrics(correlation=0.8, lr_balance_db=0.2),
        ),
        timeline=[
            TimelineRegion(
                start_sec=0,
                end_sec=10,
                content={"speech": 0.7, "music": 0.2, "ambience": 0.1},
                label=ContentLabel.speech_dominant,
            )
        ],
        issues=[
            AnalysisIssue(
                id="hum",
                severity=0.7,
                confidence=0.85,
                recoverability=Recoverability.recoverable,
                evidence={"f0_hz": 60},
                regions=[{"start_sec": 0, "end_sec": 10}],
                user_message="hum",
            )
        ],
        versions={},
        created_at="2026-01-01T00:00:00Z",
    )


def test_hum_enables_notch():
    p = plan(_analysis_with_hum(), RestorationSettings())
    hum = next(s for s in p.stages if s.id.value == "hum_notch")
    assert hum.enabled is True
    assert hum.params["f0_hz"] == 60


def test_music_blocks_speech_denoise():
    a = _analysis_with_hum()
    a.timeline[0].label = ContentLabel.music_dominant
    a.timeline[0].content = {"speech": 0.1, "music": 0.8, "ambience": 0.1}
    a.issues.append(
        AnalysisIssue(
            id="hiss",
            severity=0.8,
            confidence=0.9,
            recoverability=Recoverability.partial,
            evidence={},
            regions=[{"start_sec": 0, "end_sec": 10}],
            user_message="hiss",
        )
    )
    p = plan(a, RestorationSettings())
    dfn = next(s for s in p.stages if s.id.value == "denoise_speech")
    assert dfn.enabled is False
    assert "music" in dfn.reason.lower()


def test_music_with_speech_enables_gated_dfn():
    a = _analysis_with_hum()
    a.timeline[0].label = ContentLabel.music_dominant
    a.timeline[0].content = {"speech": 0.35, "music": 0.55, "ambience": 0.1}
    a.issues.append(
        AnalysisIssue(
            id="hiss",
            severity=0.8,
            confidence=0.9,
            recoverability=Recoverability.partial,
            evidence={},
            regions=[{"start_sec": 0, "end_sec": 10}],
            user_message="hiss",
        )
    )
    p = plan(a, RestorationSettings())
    dfn = next(s for s in p.stages if s.id.value == "denoise_speech")
    # Only if CLI is present on this machine
    from audiorestorer_engine.adapters.deepfilternet import is_available

    if is_available():
        assert dfn.enabled is True
        assert dfn.params.get("gate_with_vad") is True
    else:
        assert dfn.enabled is False
