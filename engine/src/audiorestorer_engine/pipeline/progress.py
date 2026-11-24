"""Progress / cancel callbacks for long-running jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


class CancelledError(RuntimeError):
    pass


ProgressFn = Callable[[float, str, str | None], None]  # progress 0..1, stage, message
CancelFn = Callable[[], bool]


@dataclass
class JobContext:
    progress: ProgressFn | None = None
    is_cancelled: CancelFn = field(default_factory=lambda: (lambda: False))

    def report(self, progress: float, stage: str, message: str | None = None) -> None:
        if self.is_cancelled():
            raise CancelledError("Job cancelled")
        if self.progress:
            self.progress(max(0.0, min(1.0, progress)), stage, message)
        # Allow UI cancel handlers that flip the flag inside the progress callback
        if self.is_cancelled():
            raise CancelledError("Job cancelled")

    def check(self) -> None:
        if self.is_cancelled():
            raise CancelledError("Job cancelled")
