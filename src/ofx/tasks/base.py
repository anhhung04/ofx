"""Base task class and option definition for security tool wrappers.

A *Task* wraps an external CLI tool with:
- Declarative option mapping (Python kwargs → CLI flags)
- Structured output parsing (raw stdout/file → list[OutputType])
- Install / health-check logic
- Metadata (name, description, category, output_types)
"""

from __future__ import annotations

import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ofx.tasks.output_types import OutputType


@dataclass
class OptDef:
    """Definition for a single CLI option on a task."""

    flag: str
    type: type = str
    is_flag: bool = False
    help: str = ""
    default: Any = None
    short: str = ""


class Task(ABC):
    """Abstract base class for all security tool wrappers.

    Subclass this, set the class attributes, and implement
    ``parse_output`` to integrate a new tool.
    """

    # ── Metadata (override in subclasses) ──────────────────────────
    name: str = ""
    cmd: str = ""
    description: str = ""
    category: str = ""
    install_cmd: str = ""
    output_types: list[type[OutputType]] = []

    # ── Option mapping ─────────────────────────────────────────────
    opts: dict[str, OptDef] = {}
    input_flag: str | None = None
    file_flag: str | None = None
    output_flag: str | None = None

    # ── Extra flags (override in subclasses) ─────────────────────
    # Flags prepended right after the command binary (e.g. ``["-json", "-silent"]``).
    extra_flags: list[str] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Ensure mutable class attributes are copied per-subclass.

        Without this, a subclass that doesn't explicitly set ``opts``,
        ``extra_flags``, or ``output_types`` would share the parent's
        mutable object, risking cross-class mutation.
        """
        super().__init_subclass__(**kwargs)
        for attr in ("opts", "extra_flags", "output_types"):
            value = cls.__dict__.get(attr)
            if value is None:
                # Subclass didn't define it — copy from parent
                inherited = getattr(cls, attr)
                if isinstance(inherited, dict):
                    setattr(cls, attr, dict(inherited))
                elif isinstance(inherited, list):
                    setattr(cls, attr, list(inherited))

    # ── Public API ─────────────────────────────────────────────────

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build the full CLI command string from *target* and keyword options.

        Returns ``(command_string, output_file_or_none)``.

        Subclasses that only need to add extra fixed flags should set
        :attr:`extra_flags` instead of overriding this method.
        """
        parts: list[str] = [self.cmd, *self.extra_flags]
        output_file: Path | None = None

        # Map keyword arguments to CLI flags
        for key, value in kwargs.items():
            if key.startswith("_"):
                continue
            opt = self.opts.get(key)
            if opt is None:
                continue
            if opt.is_flag:
                if value:
                    parts.append(opt.flag)
            elif value is not None:
                parts.extend([opt.flag, str(value)])

        # Output file for tools that write structured output to a file
        if self.output_flag:
            output_file = Path(
                tempfile.mkstemp(
                    prefix=f".ofx_task_{self.name}_", suffix=self._output_suffix()
                )[1]
            )
            parts.extend([self.output_flag, str(output_file)])

        # Target handling
        if self.input_flag:
            parts.extend([self.input_flag, target])
        else:
            parts.append(target)

        return " ".join(parts), output_file

    @abstractmethod
    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[OutputType]:
        """Parse raw tool output into structured ``OutputType`` objects.

        Override this in every task subclass.
        """
        ...

    def check_installed(self) -> bool:
        """Return ``True`` if the tool binary is on ``$PATH``."""
        return shutil.which(self.cmd) is not None

    def get_install_command(self) -> str | None:
        """Return shell command to install the tool, or ``None``."""
        return self.install_cmd or None

    # ── Helpers ────────────────────────────────────────────────────

    def _output_suffix(self) -> str:
        """File suffix for the structured output file."""
        return ".xml"

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
