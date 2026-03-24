"""jsluice — JS secret and endpoint extraction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("jsluice")
class JsluiceTask(Task):
    name = "jsluice"
    cmd = "jsluice"
    description = "JavaScript secret and endpoint extraction"
    category = "web/js"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v github.com/BishopFox/jsluice/cmd/jsluice@latest"
    )
    output_types = [Url, Tag]

    opts = {
        "patterns": OptDef(flag="-p", type=str, help="Custom patterns file"),
        "threads": OptDef(flag="-c", type=int, help="Concurrency"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["urls"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Handle mode as subcommand and target as positional argument."""
        mode = kwargs.pop("mode", None) or "urls"
        parts: list[str] = [self.cmd, mode]

        for key, value in kwargs.items():
            if key.startswith("_"):
                continue
            opt = self.opts.get(key)
            if opt is None or not opt.flag:
                continue
            if opt.is_flag:
                if value:
                    parts.append(opt.flag)
            elif value is not None:
                parts.extend([opt.flag, str(value)])

        if target:
            parts.append(target)

        return " ".join(parts), None

    def parse_line(self, line: str) -> list[Url | Tag]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        kind = data.get("kind", "")
        results: list[Url | Tag] = []

        if kind in ("endpoint", "linkage", ""):
            url = data.get("url", data.get("value", ""))
            if url:
                results.append(Url(url=url))
        if kind == "secret":
            secret_type = data.get("type", "secret")
            secret_data = data.get("data", data.get("value", ""))
            results.append(
                Tag(
                    name=secret_type,
                    value=secret_data,
                    category="secret",
                    extra_data={
                        k: v
                        for k, v in {
                            "severity": data.get("severity"),
                            "source": data.get("source"),
                        }.items()
                        if v
                    },
                )
            )

        return results

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url | Tag]:
        results: list[Url | Tag] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
