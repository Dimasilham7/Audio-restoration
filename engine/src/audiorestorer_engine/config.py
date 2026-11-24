"""Resolve ffmpeg / ffprobe / deep-filter paths from env (no hardcoded drives)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _meipass() -> Path | None:
    """PyInstaller onedir/onefile unpack root."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


def bin_dir() -> Path | None:
    env = os.environ.get("AUDIORESTORER_BIN_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    # Packaged Electron: resources/bin next to engine or via ELECTRON resources
    meipass = _meipass()
    if meipass:
        cand = meipass.parent / "bin"
        if cand.is_dir():
            return cand
        cand = meipass / "bin"
        if cand.is_dir():
            return cand
    # Dev: repo .models sibling / packaging/bin
    here = Path(__file__).resolve()
    for parent in here.parents:
        for rel in ("packaging/bin", "apps/desktop/resources/bin", "resources/bin"):
            cand = parent / rel
            if cand.is_dir():
                return cand
    return None


def which_tool(name: str, env_key: str) -> str:
    """Resolve an executable: env override → BIN_DIR → PATH."""
    env = os.environ.get(env_key)
    if env and Path(env).is_file():
        return str(Path(env))

    bd = bin_dir()
    if bd:
        for candidate in (bd / name, bd / f"{name}.exe"):
            if candidate.is_file():
                return str(candidate)

    found = shutil.which(name) or shutil.which(f"{name}.exe")
    if found:
        return found
    raise FileNotFoundError(
        f"{name} not found. Set {env_key} or AUDIORESTORER_BIN_DIR, or install on PATH."
    )


def ffmpeg_path() -> str:
    return which_tool("ffmpeg", "AUDIORESTORER_FFMPEG")


def ffprobe_path() -> str:
    return which_tool("ffprobe", "AUDIORESTORER_FFPROBE")


def deep_filter_path() -> Path | None:
    try:
        return Path(which_tool("deep-filter", "AUDIORESTORER_DFN_EXE"))
    except FileNotFoundError:
        # Also check .models layout used in development
        env = os.environ.get("AUDIORESTORER_DFN_EXE")
        if env and Path(env).is_file():
            return Path(env)
        here = Path(__file__).resolve()
        for parent in here.parents:
            cand = parent / ".models" / "deepfilternet" / "deep-filter.exe"
            if cand.is_file():
                return cand
            cand2 = parent / ".models" / "deepfilternet" / "deep-filter"
            if cand2.is_file():
                return cand2
        return None
