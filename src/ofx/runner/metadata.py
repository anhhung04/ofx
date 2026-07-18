"""Shared runner/model metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ModelContext:
    """Structured metadata extracted from a runner model."""

    name: str | None = None
    jid: str | None = None
    step_index: int | str | None = None

    @classmethod
    def from_model(cls, model: Any) -> ModelContext:
        return cls(
            name=getattr(model, "name", None),
            jid=getattr(model, "jid", None),
            step_index=getattr(model, "step_index", None),
        )

__all__ = ["ModelContext"]
