"""trufflehog — find leaked credentials in git repos and more."""

from __future__ import annotations

import os
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
    json_flag = "--json"
    extra_flags = ["--no-update"]

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Prepend scan mode subcommand before flags and target.

        Use ``mode`` kwarg to select git (default), filesystem, s3, etc.
        """
        mode = kwargs.pop("mode", "git")
        parts: list[str] = [self.cmd, mode, *self.extra_flags]

        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

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
            _fd, _path = tempfile.mkstemp(
                prefix=f".ofx_task_{self.name}_",
                suffix=self._output_suffix(),
            )
            os.close(_fd)
            output_file = Path(_path)
            parts.extend([self.output_flag, str(output_file)])

        parts.append(target)

        return " ".join(parts), output_file

    def parse_line(self, line: str) -> list[Tag]:
        data = self._parse_json_line(line)
        if data is None:
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

