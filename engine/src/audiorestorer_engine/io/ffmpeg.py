"""FFmpeg/ffprobe wrappers using argument arrays (no shell)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from audiorestorer_engine.config import ffmpeg_path, ffprobe_path


class FFmpegError(RuntimeError):
    pass


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        raise FFmpegError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr[-2000:]}"
        )
    return proc


def probe(path: str | Path) -> dict[str, Any]:
    ffprobe = ffprobe_path()
    proc = run(
        [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    return json.loads(proc.stdout)


def select_default_audio_stream(probe_data: dict[str, Any]) -> int:
    streams = [s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise FFmpegError("No audio stream found")
    for s in streams:
        if (s.get("disposition") or {}).get("default") == 1:
            return int(s["index"])
    return int(streams[0]["index"])


def extract_audio(
    media_path: str | Path,
    output_wav: str | Path,
    *,
    stream_index: int | None = None,
    sample_rate: int | None = None,
) -> dict[str, Any]:
    """Extract selected audio to float32 WAV. Returns probe + stream metadata."""
    ffmpeg = ffmpeg_path()
    media_path = Path(media_path)
    output_wav = Path(output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    info = probe(media_path)
    idx = stream_index if stream_index is not None else select_default_audio_stream(info)
    stream = next(s for s in info["streams"] if int(s["index"]) == idx)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(media_path),
        "-map",
        f"0:{idx}",
        "-vn",
        "-acodec",
        "pcm_f32le",
    ]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]
    cmd.append(str(output_wav))
    run(cmd)

    return {
        "probe": info,
        "audio_stream_index": idx,
        "start_time_sec": float(stream.get("start_time") or 0.0),
        "sample_rate": int(stream.get("sample_rate") or sample_rate or 0),
        "channels": int(stream.get("channels") or 0),
        "extracted_path": str(output_wav),
    }


def remux_replace_audio(
    video_path: str | Path,
    restored_audio_wav: str | Path,
    output_path: str | Path,
    *,
    audio_stream_index: int,
    audio_bitrate: str = "256k",
) -> None:
    """Replace one audio stream; stream-copy video when possible."""
    ffmpeg = ffmpeg_path()
    video_path = Path(video_path)
    restored_audio_wav = Path(restored_audio_wav)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    info = probe(video_path)
    audio_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    video_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]

    if len(audio_streams) == 1 and len(video_streams) >= 1:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(restored_audio_wav),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            audio_bitrate,
            "-map_metadata",
            "0",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    else:
        maps: list[str] = []
        for s in info.get("streams", []):
            idx = int(s["index"])
            if s.get("codec_type") == "audio" and idx == audio_stream_index:
                continue
            maps += ["-map", f"0:{idx}"]
        maps += ["-map", "1:a:0"]
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(restored_audio_wav),
            *maps,
            "-c",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            audio_bitrate,
            "-map_metadata",
            "0",
            str(output_path),
        ]
    run(cmd)


def measure_loudness_ffmpeg(audio_path: str | Path) -> dict[str, float]:
    """Use ffmpeg ebur128 filter; parse integrated loudness and true peak."""
    ffmpeg = ffmpeg_path()
    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(audio_path),
            "-filter_complex",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    text = proc.stderr
    integrated = _parse_last_float(text, "I:")
    lra = _parse_last_float(text, "LRA:")
    true_peak = _parse_last_float(text, "Peak:")
    if integrated is None or true_peak is None:
        return {"integrated_lufs": float("nan"), "lra": lra or 0.0, "true_peak_dbtp": float("nan")}
    return {
        "integrated_lufs": integrated,
        "lra": lra or 0.0,
        "true_peak_dbtp": true_peak,
    }


def _parse_last_float(text: str, label: str) -> float | None:
    values: list[float] = []
    for line in text.splitlines():
        if label not in line:
            continue
        try:
            after = line.split(label, 1)[1].strip().split()[0]
            values.append(float(after))
        except (IndexError, ValueError):
            continue
    return values[-1] if values else None
