"""s3scanner — S3/cloud bucket misconfiguration scanner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("s3scanner")
class S3scannerTask(Task):
    name = "s3scanner"
    cmd = "s3scanner"
    description = "S3/cloud bucket misconfiguration scanner"
    category = "recon/cloud"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/sa7mon/s3scanner@latest"
    output_types = [Vulnerability, Tag]

    opts = {
        "provider": OptDef(
            flag="-provider", type=str, help="Cloud provider: aws, gcp, digitalocean"
        ),
        "threads": OptDef(flag="-threads", type=int, help="Number of threads"),
        "write_test": OptDef(
            flag="-write", is_flag=True, help="Test write permissions"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    json_flag = "-json"
    extra_flags = ["scan"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Target is passed via ``-bucket`` or ``-bucket-file`` depending on type."""
        parts: list[str] = [self.cmd, *self.extra_flags]

        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        parts.extend(self._build_opt_parts(kwargs))

        if target and not target.startswith("http") and Path(target).is_file():
            parts.extend(["-bucket-file", self._q(target)])
        elif target:
            parts.extend(["-bucket", self._q(target)])

        return " ".join(parts), None

    def parse_line(self, line: str) -> list[Vulnerability | Tag]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        bucket_name = data.get("name", data.get("bucket", ""))
        if not bucket_name:
            return []

        results: list[Vulnerability | Tag] = [
            Tag(name=bucket_name, value=data.get("region", ""), category="s3")
        ]

        perms = data.get("permissions", data.get("bucket_permissions", {}))
        if isinstance(perms, dict):
            misconfigs = [k for k, v in perms.items() if v is True]
            if misconfigs:
                results.append(
                    Vulnerability(
                        name="S3 Bucket Misconfiguration",
                        matched_at=bucket_name,
                        severity=Severity.HIGH,
                        provider="s3scanner",
                        description=f"Public permissions: {', '.join(misconfigs)}",
                        extra_data={"permissions": perms},
                    )
                )

        exists = data.get("exists")
        if exists is not None and not exists:
            results = [Tag(name=bucket_name, value="not_found", category="s3")]

        return results
