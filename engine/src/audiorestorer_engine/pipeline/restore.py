"""Orchestrate analysis → plan → DSP stages with progress/cancel."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
from scipy import signal

from audiorestorer_engine.analysis.analyzer import analyze_audio
from audiorestorer_engine.dsp import filters
from audiorestorer_engine.dsp.loudness import measure_loudness, normalize_loudness
from audiorestorer_engine.io.audio import match_length, read_audio, write_audio
from audiorestorer_engine.io.ffmpeg import extract_audio, probe, remux_replace_audio
from audiorestorer_engine.pipeline.progress import JobContext
from audiorestorer_engine.planning.planner import plan as build_plan
from audiorestorer_engine.schemas import (
    ProcessReport,
    RestorationSettings,
    StageId,
    TreatmentPlan,
)

WORKING_SR = 48000
CHUNK_SAMPLES = WORKING_SR * 10  # ~10 s


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return audio.astype(np.float32)
    gcd = np.gcd(orig_sr, target_sr)
    up = target_sr // gcd
    down = orig_sr // gcd
    channels = [signal.resample_poly(ch, up, down).astype(np.float32) for ch in audio]
    min_len = min(c.shape[-1] for c in channels)
    return np.stack([c[:min_len] for c in channels], axis=0)


def apply_plan(
    audio: np.ndarray,
    sample_rate: int,
    treatment: TreatmentPlan,
    *,
    ctx: JobContext | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Apply enabled DSP stages. Returns restored audio and stage id list."""
    ctx = ctx or JobContext()
    out = audio.astype(np.float32, copy=True)
    target_len = out.shape[-1]
    applied: list[str] = []
    enabled = {s.id: s for s in treatment.stages if s.enabled}
    stages = [s for s in treatment.stages if s.enabled]
    n_stages = max(1, len(stages))

    def _mark(i: int, stage_id: str) -> None:
        ctx.report(0.35 + 0.45 * (i / n_stages), stage_id, f"Applying {stage_id}")

    step = 0
    if StageId.condition in enabled:
        _mark(step, StageId.condition.value)
        out = filters.dc_block(out, sample_rate)
        applied.append(StageId.condition.value)
        step += 1

    if StageId.declip in enabled:
        _mark(step, StageId.declip.value)
        thr = float(enabled[StageId.declip].params.get("threshold", 0.99))
        out = filters.soft_declip(out, threshold=thr)
        applied.append(StageId.declip.value)
        step += 1

    if StageId.hum_notch in enabled:
        _mark(step, StageId.hum_notch.value)
        p = enabled[StageId.hum_notch].params
        out = filters.notch_comb(
            out,
            sample_rate,
            f0=float(p.get("f0_hz", 50)),
            harmonics=int(p.get("harmonics", 5)),
            q=float(p.get("q", 35)),
        )
        applied.append(StageId.hum_notch.value)
        step += 1

    if StageId.wind_rumble in enabled:
        _mark(step, StageId.wind_rumble.value)
        cutoff = float(enabled[StageId.wind_rumble].params.get("cutoff_hz", 80))
        out = filters.highpass(out, sample_rate, cutoff)
        applied.append(StageId.wind_rumble.value)
        step += 1

    if StageId.denoise_speech in enabled:
        _mark(step, StageId.denoise_speech.value)
        from audiorestorer_engine.adapters.deepfilternet import (
            enhance as dfn_enhance,
            mix_wet_dry,
            speech_activity_mask,
        )

        p = enabled[StageId.denoise_speech].params
        atten = float(p.get("atten_lim_db", 12.0))
        dry = out
        ctx.check()
        wet = dfn_enhance(
            out,
            sample_rate,
            atten_lim_db=atten,
            compensate_delay=bool(p.get("compensate_delay", True)),
            is_cancelled=ctx.is_cancelled,
        )
        ctx.check()
        if p.get("gate_with_vad", False):
            mask = speech_activity_mask(dry, sample_rate)
            out = mix_wet_dry(dry, wet, mask)
        else:
            out = wet
        applied.append(StageId.denoise_speech.value)
        step += 1

    if StageId.denoise_music_gate in enabled:
        _mark(step, StageId.denoise_music_gate.value)
        red = float(enabled[StageId.denoise_music_gate].params.get("reduction_db", -6))
        out = filters.high_shelf(out, sample_rate, freq=6000.0, gain_db=red)
        applied.append(StageId.denoise_music_gate.value)
        step += 1

    if StageId.tonal_eq in enabled:
        _mark(step, StageId.tonal_eq.value)
        p = enabled[StageId.tonal_eq].params
        hs = float(p.get("high_shelf_db", 0))
        if abs(hs) >= 0.25:
            out = filters.high_shelf(
                out,
                sample_rate,
                freq=float(p.get("high_shelf_hz", 3500)),
                gain_db=hs,
            )
        bass = float(p.get("bass_db", 0))
        if abs(bass) >= 0.25:
            out = filters.peaking_eq(
                out,
                sample_rate,
                freq=float(p.get("bass_hz", 120)),
                gain_db=bass,
                q=0.8,
            )
        applied.append(StageId.tonal_eq.value)
        step += 1

    if StageId.stereo in enabled:
        _mark(step, StageId.stereo.value)
        p = enabled[StageId.stereo].params
        bal = float(p.get("lr_balance_db", 0.0))
        if abs(bal) >= 0.5:
            out = filters.balance_lr(out, bal)
        width = float(p.get("width", 1.0))
        if abs(width - 1.0) > 0.05:
            out = filters.stereo_width(out, width)
        applied.append(StageId.stereo.value)
        step += 1

    if StageId.loudness in enabled:
        _mark(step, StageId.loudness.value)
        target = float(enabled[StageId.loudness].params.get("target_lufs", -16))
        # Two-pass friendly: measure then apply constant gain in chunks
        measured = measure_loudness(out, sample_rate)["integrated_lufs"]
        if np.isfinite(measured) and measured > -70:
            gain = 10 ** ((target - measured) / 20.0)
            out = _apply_gain_chunked(out, gain, ctx, StageId.loudness.value)
        else:
            out = normalize_loudness(out, sample_rate, target_lufs=target)
        applied.append(StageId.loudness.value)
        step += 1

    if StageId.limiter in enabled:
        _mark(step, StageId.limiter.value)
        ceiling = float(enabled[StageId.limiter].params.get("ceiling_dbtp", -1.0))
        out = filters.true_peak_limit(out, ceiling_dbtp=ceiling)
        applied.append(StageId.limiter.value)
        step += 1

    out = match_length(out, target_len)
    ctx.report(0.85, "dsp", "DSP complete")
    return out.astype(np.float32), applied


def _apply_gain_chunked(
    audio: np.ndarray,
    gain: float,
    ctx: JobContext,
    stage: str,
) -> np.ndarray:
    out = np.empty_like(audio, dtype=np.float32)
    n = audio.shape[-1]
    for start in range(0, n, CHUNK_SAMPLES):
        ctx.check()
        end = min(n, start + CHUNK_SAMPLES)
        out[..., start:end] = (audio[..., start:end] * gain).astype(np.float32)
        ctx.report(0.5 + 0.3 * (end / n), stage, f"Gain chunk {end}/{n}")
    return out


def process_media(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    settings: RestorationSettings | None = None,
    work_dir: str | Path | None = None,
    ctx: JobContext | None = None,
    on_progress: Callable[[float, str, str | None], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> ProcessReport:
    """End-to-end: extract → analyze → plan → restore → remux/write."""
    ctx = ctx or JobContext(
        progress=on_progress,
        is_cancelled=is_cancelled or (lambda: False),
    )
    input_path = Path(input_path)
    settings = settings or RestorationSettings()
    work_dir = Path(work_dir or (input_path.parent / ".audiorestorer_work" / input_path.stem))
    work_dir.mkdir(parents=True, exist_ok=True)

    ctx.report(0.02, "probe", "Probing media")
    info = probe(input_path)
    has_video = any(s.get("codec_type") == "video" for s in info.get("streams", []))

    extracted = work_dir / "extracted.wav"
    ctx.report(0.08, "extract", "Extracting audio")
    meta = extract_audio(input_path, extracted)
    ctx.check()

    ctx.report(0.15, "load", "Loading audio")
    audio, sr = read_audio(extracted)
    original_len = audio.shape[-1]
    original_sr = sr

    ctx.report(0.2, "resample", "Resampling" if sr != WORKING_SR else "Using native 48 kHz")
    audio_w = _resample(audio, sr, WORKING_SR)
    del audio  # free original buffer early when resampled

    ctx.report(0.28, "analyze", "Analyzing")
    analysis = analyze_audio(audio_w, WORKING_SR, media_id=input_path.name)
    treatment = build_plan(analysis, settings)

    restored_w, applied = apply_plan(audio_w, WORKING_SR, treatment, ctx=ctx)
    del audio_w

    ctx.report(0.88, "resample_out", "Writing restored audio")
    restored = _resample(restored_w, WORKING_SR, original_sr)
    del restored_w
    restored = match_length(restored, original_len)

    restored_wav = work_dir / "restored.wav"
    write_audio(restored_wav, restored, original_sr)

    sample_count_ok = restored.shape[-1] == original_len
    out_media: Path | None = None
    warnings = list(treatment.warnings)

    ctx.report(0.92, "export", "Exporting")
    if has_video:
        if output_path is None:
            output_path = input_path.with_name(f"{input_path.stem}.restored.mp4")
        out_media = Path(output_path)
        remux_replace_audio(
            input_path,
            restored_wav,
            out_media,
            audio_stream_index=meta["audio_stream_index"],
        )
    else:
        if output_path is None:
            output_path = input_path.with_name(f"{input_path.stem}.restored.wav")
        out_media = Path(output_path)
        write_audio(out_media, restored, original_sr)

    if not sample_count_ok:
        warnings.append("Sample count mismatch after resampling; padded/trimmed to match.")

    ctx.report(1.0, "done", "Complete")
    return ProcessReport(
        analysis=analysis,
        plan=treatment,
        settings=settings,
        input_path=str(input_path),
        output_audio_path=str(restored_wav),
        output_media_path=str(out_media) if out_media else None,
        warnings=warnings,
        sample_count_ok=sample_count_ok,
        stages_applied=applied,
    )


def analyze_media(
    input_path: str | Path,
    work_dir: str | Path | None = None,
    *,
    ctx: JobContext | None = None,
) -> ProcessReport:
    """Analyze only."""
    ctx = ctx or JobContext()
    input_path = Path(input_path)
    work_dir = Path(work_dir or (input_path.parent / ".audiorestorer_work" / input_path.stem))
    work_dir.mkdir(parents=True, exist_ok=True)
    ctx.report(0.1, "extract", "Extracting audio")
    extracted = work_dir / "extracted.wav"
    extract_audio(input_path, extracted)
    ctx.report(0.4, "load", "Loading")
    audio, sr = read_audio(extracted)
    audio_w = _resample(audio, sr, WORKING_SR)
    ctx.report(0.7, "analyze", "Analyzing")
    analysis = analyze_audio(audio_w, WORKING_SR, media_id=input_path.name)
    settings = RestorationSettings()
    treatment = build_plan(analysis, settings)
    ctx.report(1.0, "done", "Complete")
    return ProcessReport(
        analysis=analysis,
        plan=treatment,
        settings=settings,
        input_path=str(input_path),
        output_audio_path="",
        output_media_path=None,
        warnings=treatment.warnings,
        sample_count_ok=True,
        stages_applied=[],
    )
