"""dalfox — powerful XSS scanner and parameter analysis tool."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("dalfox")
class DalfoxTask(Task):
    name = "dalfox"
    cmd = "dalfox"
    description = "Powerful open-source XSS scanner"
    category = "url/fuzz"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/hahwul/dalfox/v2@latest"
    output_types = [Vulnerability, Url]

    opts = {
        "blind": OptDef(flag="--blind", type=str, help="Blind XSS callback URL"),
        "custom_payload": OptDef(
            flag="--custom-payload", type=str, help="Custom payload file path"
        ),
        "cookie": OptDef(flag="-C", type=str, help="Cookie string"),
        "header": OptDef(flag="-H", type=str, help="Custom header"),
        "method": OptDef(flag="-X", type=str, help="HTTP method"),
        "timeout": OptDef(flag="--timeout", type=int, help="Timeout in seconds"),
        "workers": OptDef(flag="-w", type=int, help="Number of workers"),
        "delay": OptDef(flag="--delay", type=int, help="Delay between requests in ms"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["--format", "jsonl", "--silence"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Prepend 'url' or 'file' subcommand before the target."""
        parts: list[str] = [self.cmd]

        target_path = Path(target)
        if target_path.is_file():
            parts.append("file")
        else:
            parts.append("url")

        parts.extend(self.extra_flags)

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

        if self.output_flag:
            output_file = Path(
                tempfile.mkstemp(
                    prefix=f".ofx_task_{self.name}_",
                    suffix=self._output_suffix(),
                )[1]
            )
            parts.extend([self.output_flag, str(output_file)])
        else:
            output_file = None

        parts.append(target)

        return " ".join(parts), output_file

    def parse_line(self, line: str) -> list[Vulnerability | Url]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        result_type = data.get("type", "")
        if result_type == "vuln":
            return [
                Vulnerability(
                    name=data.get("data", "XSS"),
                    id=data.get("cwe", ""),
                    matched_at=data.get("inject_url", data.get("url", "")),
                    severity=Vulnerability.model_fields["severity"].default,
                    provider="dalfox",
                    description=data.get("message", ""),
                    tags=["xss"],
                )
            ]

        url = data.get("url", data.get("inject_url", ""))
        if url:
            return [Url(url=url)]

        return []

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Url]:
        results: list[Vulnerability | Url] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
