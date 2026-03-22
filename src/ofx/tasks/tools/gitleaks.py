"""gitleaks — detect secrets in source code and git repos."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("gitleaks")
class GitleaksTask(Task):
    name = "gitleaks"
    cmd = "gitleaks"
    description = "Detect secrets in source code and git repositories"
    category = "secret/scan"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/gitleaks/gitleaks/v8@latest"
    output_types = [Tag]

    opts = {
        "source": OptDef(flag="--source", type=str, help="Path or URL to scan"),
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose output"),
        "redact": OptDef(flag="--redact", is_flag=True, help="Redact secrets"),
        "config": OptDef(flag="--config", type=str, help="Config file path"),
    }

    input_flag = None
    file_flag = None
    output_flag = "--report-path"
    extra_flags = ["detect", "-f", "json", "--no-banner"]

    def _output_suffix(self) -> str:
        return ".json"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Replace positional target with --source <target>."""
        parts: list[str] = [self.cmd, *self.extra_flags]

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

        parts.extend(["--source", target])

        return " ".join(parts), output_file

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        try:
            findings = json.loads(raw)
        except json.JSONDecodeError:
            return []

        if not isinstance(findings, list):
            return []

        results: list[Tag] = []
        for item in findings:
            results.append(
                Tag(
                    name="secret",
                    value=item.get("RuleID", ""),
                    match=item.get("File", ""),
                    category="secret",
                    extra_data={
                        "line": item.get("StartLine"),
                        "commit": item.get("Commit", ""),
                        "author": item.get("Author", ""),
                    },
                )
            )

        return results
