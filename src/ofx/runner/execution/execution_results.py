"""Structured execution results for runners."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class StepExecutionResult:
    step_index: int
    name: str
    run_type: str
    status: str
    error: str | None
    outputs: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobExecutionResult:
    jid: str
    name: str
    status: str
    error: str | None
    total_steps: int
    failed_steps: list[int]
    steps: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
