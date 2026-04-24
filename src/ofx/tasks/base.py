"""Base task class and option definition for security tool wrappers.

A *Task* wraps an external CLI tool with:
- Declarative option mapping (Python kwargs → CLI flags)
- Structured output parsing (raw stdout/file → list[OutputType])
- Auto-optimized flags (json, silent, quiet) injected automatically
- Install / health-check logic
- Metadata (name, description, category, output_types)
"""

from __future__ import annotations

import os
import shutil
import tempfile
from abc import ABC
from collections.abc import Sequence
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
    ``parse_output`` (or just ``parse_line``) to integrate a new tool.
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

    # ── Subcommand ────────────────────────────────────────────────
    # Inserted after the command binary, before extra_flags.
    # e.g. ``subcommand = "image"`` → ``trivy image -f json …``
    subcommand: str = ""

    # ── Extra flags (override in subclasses) ─────────────────────
    # Flags prepended right after the command binary (and subcommand).
    extra_flags: list[str] = []

    # ── Auto-optimized flags ───────────────────────────────────────
    # Set these to auto-inject machine-friendly output flags.
    # They are appended to the command automatically.  Set to ``""``
    # to disable a particular auto-flag.
    json_flag: str = ""      # e.g. "-json", "--json", "-jsonl"
    silent_flag: str = ""    # e.g. "-silent", "--silent", "-s"

    # ── Exit code handling ─────────────────────────────────────────
    # Exit codes considered successful.  Override in subclasses for tools
    # that return non-zero on "warnings found" or similar expected states.
    success_codes: list[int] = [0]

    # ── Output export control ──────────────────────────────────────
    # Set to ``False`` for tools whose output is intermediate data
    # (e.g. permutation generators) that should not be persisted in
    # ``<output_path>/scans/``.
    export_output: bool = True

    # ── Instance state (set during build_command) ────────────────
    _temp_target_files: list[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Ensure mutable class attributes are copied per-subclass."""
        super().__init_subclass__(**kwargs)
        for attr in ("opts", "extra_flags", "output_types", "success_codes"):
            value = cls.__dict__.get(attr)
            if value is None:
                inherited = getattr(cls, attr)
                if isinstance(inherited, dict):
                    setattr(cls, attr, dict(inherited))
                elif isinstance(inherited, list):
                    setattr(cls, attr, list(inherited))

    def __init__(self) -> None:
        self._temp_target_files: list[str] = []

    # ── Helpers ────────────────────────────────────────────────────

    def _make_output_path(self) -> Path:
        """Reserve a unique temp path for tool output without pre-creating it.

        Uses mkstemp to guarantee uniqueness, then immediately unlinks the
        file so the external tool creates it with its own uid/permissions.
        This avoids "could not open file for writing" errors when the tool
        runs as a different user (e.g. masscan/nmap via sudo).
        """
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".ofx_task_{self.name}_", suffix=self._output_suffix()
        )
        os.close(fd)
        os.unlink(tmp_path)
        return Path(tmp_path)

    # ── Public API ─────────────────────────────────────────────────

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build the full CLI command string from *target* and keyword options.

        Returns ``(command_string, output_file_or_none)``.

        Subclasses that only need to add extra fixed flags should set
        :attr:`extra_flags` instead of overriding this method.
        """
        if not target:
            raise ValueError(f"Task '{self.name}' requires a non-empty target")

        parts: list[str] = [self.cmd]
        if self.subcommand:
            parts.append(self.subcommand)
        parts.extend(self.extra_flags)
        output_file: Path | None = None

        # Auto-inject optimized flags
        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

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
            output_file = self._make_output_path()
            parts.extend([self.output_flag, str(output_file)])

        # Target handling — auto-detect file paths, multi-target lists
        target_is_file = (
            self.file_flag
            and target
            and not target.startswith("http")
            and Path(target).is_file()
        )
        is_multi = "," in target and not Path(target).is_file() if target else False

        if target_is_file and self.file_flag:
            parts.extend([self.file_flag, target])
        elif is_multi and self.file_flag:
            parts.extend([self.file_flag, self._write_target_file(target)])
        elif is_multi and not self.file_flag:
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

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> Sequence[OutputType]:
        """Parse raw tool output into structured ``OutputType`` objects.

        Default implementation reads lines from output_file (or stdout)
        and delegates to :meth:`parse_line`.  Tasks with custom parsing
        (XML, full JSON, etc.) should override this method.
        """
        results: list[OutputType] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results

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

        Auto-detected: ``True`` when a subclass overrides :meth:`parse_line`.
        """
        return type(self).parse_line is not Task.parse_line

    def parse_line(self, line: str) -> Sequence[OutputType]:
        """Parse a single stdout line into output items (for live streaming).

        Override in subclasses whose tool emits JSONL or line-delimited
        output.  Return an empty list for non-parseable lines.
        """
        return []

    def _write_target_file(self, target: str) -> str:
        """Write comma-separated targets to a temp file, one per line."""
        tf = tempfile.NamedTemporaryFile(
            mode="w",
            prefix=f".ofx_targets_{self.name}_",
            suffix=".txt",
            delete=False,
        )
        tf.write("\n".join(t.strip() for t in target.split(",") if t.strip()))
        tf.close()
        self._temp_target_files.append(tf.name)
        return tf.name

    def cleanup_target_files(self) -> None:
        """Remove temporary target files created by :meth:`build_command`."""
        for path in self._temp_target_files:
            try:
                os.unlink(path)
            except OSError:
                pass
        self._temp_target_files.clear()

    def _output_suffix(self) -> str:
        """File suffix for the structured output file."""
        return ".xml"

    @staticmethod
    def _parse_json_line(line: str) -> dict | None:
        """Parse a single JSONL line, returning the dict or ``None``."""
        import json

        line = line.strip()
        if not line or not line.startswith("{"):
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def _read_json_output(
        self, stdout: str, output_file: Path | None = None
    ) -> Any | None:
        """Read and parse JSON from *output_file* or *stdout*.

        Returns the parsed object or ``None`` on failure.
        """
        import json

        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _read_output_file(path: Path) -> str:
        """Read an output file, returns empty string on failure."""
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
