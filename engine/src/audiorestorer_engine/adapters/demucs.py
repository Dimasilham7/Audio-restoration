"""Optional V2 Demucs adapter (not bundled — license-gated)."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np


class DemucsUnavailable(RuntimeError):
    pass


def is_available() -> bool:
    if os.environ.get("AUDIORESTORER_ENABLE_DEMUCS", "").lower() not in ("1", "true", "yes"):
        return False
    try:
        import demucs  # noqa: F401

        return True
    except Exception:
        return False


def separate(
    audio: np.ndarray,
    sample_rate: int,
    *,
    model: str = "htdemucs",
) -> dict[str, np.ndarray]:
    """
    Return stems dict. Requires opt-in env + installed demucs + accepted license.

    Weights are NOT redistributed by AudioRestorer AI.
    """
    if not is_available():
        raise DemucsUnavailable(
            "Demucs disabled or not installed. Set AUDIORESTORER_ENABLE_DEMUCS=1 "
            "and install demucs only after accepting weight license uncertainty."
        )
    raise DemucsUnavailable(
        f"Demucs runtime path not fully wired for model={model}; "
        "scaffold only until license-cleared weights are provided locally."
    )


def default_model_dir() -> Path | None:
    env = os.environ.get("AUDIORESTORER_DEMUCS_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return None
