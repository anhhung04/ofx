"""trufflehog — find leaked credentials in git repos and more."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry

_BARE_DOMAIN_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)+(/.*)?$"
)

@TaskRegistry.register("trufflehog")
class TrufflehogTask(Task):
    name = "trufflehog"
    cmd = "trufflehog"
    description = "Find leaked credentials in git repos, filesystems, and more"
    category = "secret/scan"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/trufflesecurity/trufflehog/v3@latest"
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

    @staticmethod
    def _normalize_git_target(target: str) -> str:
        """Ensure *target* is a valid Git URI for ``trufflehog git``.

        Bare domains like ``example.com`` or ``example.com/org/repo`` are
        prefixed with ``https://`` so trufflehog can clone them.  Targets
        that already carry a scheme, look like SSH URIs, or point to a
        local path are returned unchanged.
        """
        stripped = target.strip()
        if not stripped:
            return stripped

        if re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://", stripped):
            return stripped

        if re.match(r"^[^/@]+@[^:]+:", stripped):
            return stripped

        if stripped.startswith(("/", ".", "~")) or Path(stripped).is_dir():
            return stripped

        if _BARE_DOMAIN_RE.match(stripped):
            return f"https://{stripped}"

        return stripped

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Prepend scan mode subcommand before flags and target.

        Use ``mode`` kwarg to select git (default), filesystem, s3, etc.
        """
        mode = kwargs.pop("mode", "git")

        if mode == "git":
            target = self._normalize_git_target(target)

        parts: list[str] = [self.cmd, mode, *self.extra_flags]

        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        parts.extend(self._build_opt_parts(kwargs))

        output_file: Path | None = None
        if self.output_flag:
            output_file = self._make_output_path()
            parts.extend([self.output_flag, str(output_file)])

        parts.append(self._q(target))

        return " ".join(parts), output_file

    def parse_line(self, line: str) -> list[Tag]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        source_meta = data.get("SourceMetadata", {}).get("Data", {})
        file_path = source_meta.get("Filesystem", {}).get("file", "")
        if not file_path:
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
