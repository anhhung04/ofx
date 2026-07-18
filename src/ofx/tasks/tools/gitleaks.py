"""gitleaks — detect secrets in source code and git repos."""

from __future__ import annotations

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
    install_cmd = (
        "GOBIN=$TOOLS_BIN_DIR go install -v github.com/gitleaks/gitleaks/v8@latest"
    )
    output_types = [Tag]

    success_codes = [0, 1]

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

        parts.extend(self._build_opt_parts(kwargs))

        output_file: Path | None = None
        if self.output_flag:
            output_file = self._make_output_path()
            parts.extend([self.output_flag, str(output_file)])

        parts.extend(["--source", self._q(target)])

        return " ".join(parts), output_file

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        if not isinstance(data, list):
            return []

        results: list[Tag] = []
        for item in data:
            rule_id = item.get("RuleID", "")
            if not rule_id:
                continue
            results.append(
                Tag(
                    name=rule_id,
                    value=item.get("Match", rule_id),
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
