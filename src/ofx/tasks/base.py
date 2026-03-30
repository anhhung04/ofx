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

    def __post_init__(self) -> None:
        if not self.flag or not self.flag.strip():
            raise ValueError("OptDef.flag must be a non-empty string")


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

        # Target handling — auto-detect file paths, multi-target lists,
        # and choose the safest CLI flag for the tool.
        target_is_file = (
            self.file_flag
            and target
            and not target.startswith("http")
            and Path(target).is_file()
        )
        is_multi = "," in target and not Path(target).is_file() if target else False

        if target_is_file:
            parts.extend([self.file_flag, target])
        elif is_multi and self.file_flag:
            # Tool supports file input — write comma-separated targets to a
            # temp file so each target is on its own line.
            parts.extend([self.file_flag, self._write_target_file(target)])
        elif is_multi and not self.file_flag:
            # Tool has NO file_flag — write targets to a temp file and pipe
            # via stdin so tools that read stdin still work.  Tools that only
            # accept a single positional/flag target will receive the file
            # path instead, which is safer than a mangled comma string.
            tfile = self._write_target_file(target)
            if self.input_flag:
                parts.extend([self.input_flag, tfile])
            else:
                parts.append(tfile)
        elif self.input_flag:
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

    @property
    def supports_streaming(self) -> bool:
        """Whether the task supports line-by-line live streaming.

        Tasks that output JSONL or one-result-per-line can override this
        to return ``True``.  The default is ``True`` for tasks that define
        :meth:`parse_line`.
        """
        return type(self).parse_line is not Task.parse_line

    def parse_line(self, line: str) -> list[OutputType]:
        """Parse a single stdout line into output items (for live streaming).

        Override in subclasses whose tool emits JSONL or line-delimited
        output.  Return an empty list for non-parseable lines.

        The default implementation returns ``[]`` (no streaming support).
        """
        return []

    def _write_target_file(self, target: str) -> str:
        """Write comma-separated targets to a temp file, one per line.

        Returns the path to the temp file.
        """
        tf = tempfile.NamedTemporaryFile(
            mode="w",
            prefix=f".ofx_targets_{self.name}_",
            suffix=".txt",
            delete=False,
        )
        tf.write("\n".join(t.strip() for t in target.split(",") if t.strip()))
        tf.close()
        return tf.name

    def _output_suffix(self) -> str:
        """File suffix for the structured output file."""
        return ".xml"

    @staticmethod
    def _read_output_file(path: Path) -> str:
        """Read an output file with error handling.

        Returns empty string on any read failure (permission, encoding, etc.).
        """
        try:
            return path.read_text(errors="replace")
        except OSError:
            return ""

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
