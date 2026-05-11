"""jsluice — JS secret and endpoint extraction."""

from __future__ import annotations

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
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/BishopFox/jsluice/cmd/jsluice@latest"
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
                parts.extend([opt.flag, self._q(value)])

        if target:
            parts.append(self._q(target))

        return " ".join(parts), None

    def parse_line(self, line: str) -> list[Url | Tag]:
        data = self._parse_json_line(line)
        if data is None:
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
