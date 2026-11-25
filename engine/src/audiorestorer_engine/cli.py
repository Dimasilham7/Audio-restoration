"""Typer CLI entrypoint."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from audiorestorer_engine.pipeline.restore import analyze_media, process_media
from audiorestorer_engine.schemas import Preset, RestorationSettings

app = typer.Typer(add_completion=False, no_args_is_help=True, help="AudioRestorer AI engine")
console = Console()


@app.command()
def analyze(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    json_out: Optional[Path] = typer.Option(None, "--json", help="Write AnalysisResult JSON"),
) -> None:
    """Analyze media and print diagnosis."""
    report = analyze_media(input_path)
    a = report.analysis
    console.print(f"[bold]File:[/bold] {input_path.name}")
    console.print(
        f"Duration {a.duration_sec:.2f}s | {a.sample_rate} Hz | {a.channels} ch | "
        f"LUFS {a.global_metrics.loudness.integrated_lufs:.1f} | "
        f"TP {a.global_metrics.loudness.true_peak_dbtp:.1f} dBTP"
    )
    if a.timeline:
        t = a.timeline[0]
        console.print(
            f"Content: {t.label.value} "
            f"(speech={t.content.get('speech', 0):.2f}, music={t.content.get('music', 0):.2f})"
        )

    table = Table(title="Issues")
    table.add_column("ID")
    table.add_column("Severity")
    table.add_column("Confidence")
    table.add_column("Recoverability")
    table.add_column("Message")
    for issue in a.issues:
        table.add_row(
            issue.id,
            f"{issue.severity:.2f}",
            f"{issue.confidence:.2f}",
            issue.recoverability.value,
            issue.user_message,
        )
    console.print(table)

    console.print("[bold]Recommended stages:[/bold]")
    for stage in report.plan.stages:
        if stage.enabled:
            console.print(f"  - {stage.id.value}: {stage.reason}")

    if json_out:
        json_out.write_text(a.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"Wrote {json_out}")


@app.command()
def process(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    preset: Preset = typer.Option(Preset.balanced, "--preset", "-p"),
    strength: float = typer.Option(0.6, "--strength", min=0.0, max=1.0),
    loudness: float = typer.Option(-16.0, "--loudness"),
    work_dir: Optional[Path] = typer.Option(None, "--work-dir"),
) -> None:
    """Restore audio and remux video (or write restored audio)."""
    settings = RestorationSettings(preset=preset, strength=strength, loudness_target_lufs=loudness)
    console.print(f"[bold]Processing[/bold] {input_path} ...")
    report = process_media(input_path, output, settings=settings, work_dir=work_dir)
    console.print(f"[green]Done[/green] -> {report.output_media_path}")
    console.print(f"Stages: {', '.join(report.stages_applied)}")
    console.print(f"Sample count OK: {report.sample_count_ok}")
    if report.warnings:
        for w in report.warnings:
            console.print(f"[yellow]Warning:[/yellow] {w}")
    summary = {
        "output": report.output_media_path,
        "stages": report.stages_applied,
        "issues": [i.id for i in report.analysis.issues],
        "sample_count_ok": report.sample_count_ok,
    }
    console.print_json(json.dumps(summary))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(0, "--port", help="0 = ephemeral port"),
    token: Optional[str] = typer.Option(None, "--token", help="Bearer token (or AUDIORESTORER_TOKEN)"),
) -> None:
    """Start local FastAPI engine; prints READY port=NNNN for supervisors."""
    if token:
        os.environ["AUDIORESTORER_TOKEN"] = token
    if port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, 0))
            port = int(s.getsockname()[1])
    # Pass the app object directly so PyInstaller frozen builds do not need
    # uvicorn's string import of audiorestorer_engine.api.app.
    os.environ["AUDIORESTORER_PORT"] = str(port)
    from audiorestorer_engine.api.app import app as fastapi_app

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=False,
        log_level="warning",
    )


if __name__ == "__main__":
    app()
