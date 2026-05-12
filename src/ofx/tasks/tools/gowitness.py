"""gowitness — web screenshotting tool."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("gowitness")
class GowitnessTask(Task):
    name = "gowitness"
    cmd = "gowitness"
    description = "Web screenshotting tool"
    category = "url/screenshot"
    install_cmd = (
        "GOBIN=$TOOLS_BIN_DIR go install -v github.com/sensepost/gowitness@latest"
    )
    output_types = [Url, Tag]

    opts = {
        "threads": OptDef(flag="--threads", type=int, help="Number of threads"),
        "timeout": OptDef(flag="--timeout", type=int, help="Timeout in seconds"),
        "delay": OptDef(flag="--delay", type=int, help="Delay between requests"),
        "resolution": OptDef(
            flag="--resolution", type=str, help="Screenshot resolution (e.g. 1440,900)"
        ),
        "screenshot_path": OptDef(
            flag="--screenshot-path", type=str, help="Screenshot output directory"
        ),
        "fullpage": OptDef(flag="--fullpage", is_flag=True, help="Capture full page"),
        "user_agent": OptDef(flag="--user-agent", type=str, help="Custom user agent"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build gowitness command for single URL or file input."""
        file_input = kwargs.pop("_file", None)

        if file_input:
            parts: list[str] = [self.cmd, "scan", "file", "-f", self._q(file_input)]
        else:
            parts = [self.cmd, "scan", "single", "--url", self._q(target)]

        parts.extend(self._build_opt_parts(kwargs))

        return " ".join(parts), None

    # [200] https://example.com - Example Title
    _STATUS_RE = re.compile(r"\[(\d{3})\]\s+(\S+)\s*(?:-\s*(.*))?")

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url | Tag]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[Url | Tag] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            m = self._STATUS_RE.search(line)
            if m:
                results.append(
                    Url(
                        url=m.group(2),
                        status_code=self._safe_int(m.group(1)),
                        title=m.group(3).strip() if m.group(3) else "",
                    )
                )

        return results
