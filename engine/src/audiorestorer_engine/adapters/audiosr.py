"""Optional V3 AudioSR adapter (reconstruction — isolated, not bundled)."""

from __future__ import annotations

import os

import numpy as np


class AudioSRUnavailable(RuntimeError):
    pass


def is_available() -> bool:
    if os.environ.get("AUDIORESTORER_ENABLE_AUDIOSR", "").lower() not in ("1", "true", "yes"):
        return False
    try:
        import audiosr  # noqa: F401

        return True
    except Exception:
        return False


def enhance_bandwidth(
    audio: np.ndarray,
    sample_rate: int,
) -> np.ndarray:
    """
    Generative bandwidth extension. Mark outputs as AI reconstruction in UX.

    Requires isolated env + AUDIORESTORER_ENABLE_AUDIOSR=1.
    """
    if not is_available():
        raise AudioSRUnavailable(
            "AudioSR disabled or not installed. Opt-in only; treat output as reconstruction."
        )
    raise AudioSRUnavailable("AudioSR runtime scaffold only — not wired for default MVP path.")
