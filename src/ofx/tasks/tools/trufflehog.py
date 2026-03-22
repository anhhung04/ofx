"""trufflehog — find leaked credentials in git repos and more."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("trufflehog")
class TrufflehogTask(Task):
    name = "trufflehog"
    cmd = "trufflehog"
    description = "Find leaked credentials in git repos, filesystems, and more"
    category = "secret/scan"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/trufflesecurity/trufflehog/v3@latest"
    output_types = [Tag]

    opts = {
        "concurrency": OptDef(flag="-j", type=int, help="Number of concurrent workers"),
        "verified_only": OptDef(
            flag="--only-verified", is_flag=True, help="Only show verified secrets"
        ),
        "include_detectors": OptDef(
            flag="--include-detectors",
            type=str,
            help="Comma-separated list of detectors to include",
        ),
        "exclude_detectors": OptDef(
            flag="--exclude-detectors",
            type=str,
            help="Comma-separated list of detectors to exclude",
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["--json", "--no-update"]

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Prepend 'git' subcommand before flags and target."""
        parts: list[str] = [self.cmd, "git", *self.extra_flags]

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

        output_file: Path | None = None
        if self.output_flag:
            output_file = Path(
                tempfile.mkstemp(
                    prefix=f".ofx_task_{self.name}_",
                    suffix=self._output_suffix(),
                )[1]
            )
            parts.extend([self.output_flag, str(output_file)])

        parts.append(target)

        return " ".join(parts), output_file

    def parse_line(self, line: str) -> list[Tag]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        source_meta = data.get("SourceMetadata", {}).get("Data", {})
        file_path = source_meta.get("Filesystem", {}).get("file", "")
        if not file_path:
            # Fall back to Git metadata
            git_data = source_meta.get("Git", {})
            file_path = git_data.get("file", "")

        return [
            Tag(
                name="secret",
                value=data.get("DetectorName", ""),
                match=file_path,
                category="secret",
                extra_data={
                    "verified": data.get("Verified", False),
                    "raw": data.get("Raw", "")[:100],
                },
            )
        ]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        results: list[Tag] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
