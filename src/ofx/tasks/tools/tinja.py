"""tinja — SSTI injection scanner (Hackmanit TInjA)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Url, Vulnerability
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("tinja")
class TinjaTask(Task):
    name = "tinja"
    cmd = "TInjA"
    description = "Server-Side Template Injection scanner"
    category = "url/fuzz"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/Hackmanit/TInjA@latest"
    output_types = [Vulnerability, Url]

    opts = {
        "rate_limit": OptDef(flag="-ratelimit", type=int, help="Requests per second"),
        "timeout": OptDef(flag="-timeout", type=int, help="Request timeout in seconds"),
        "headers": OptDef(flag="-H", type=str, help="Custom header"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    json_flag = "-json"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Use ``url -u`` for single targets or ``url-file -f`` for files."""
        parts: list[str] = [self.cmd]

        if target and not target.startswith("http") and Path(target).is_file():
            parts.extend(["url-file", "-f", self._q(target)])
        else:
            parts.extend(["url", "-u", self._q(target)])

        parts.extend(self.extra_flags)

        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        parts.extend(self._build_opt_parts(kwargs))

        return " ".join(parts), None

    def parse_line(self, line: str) -> list[Vulnerability | Url]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        url = data.get("url", data.get("URL", ""))
        vulnerable = data.get("vulnerable", False)
        engine = data.get("engine", data.get("template_engine", ""))

        results: list[Vulnerability | Url] = []

        if url:
            results.append(Url(url=url))

        if vulnerable and url:
            results.append(
                Vulnerability(
                    name="SSTI",
                    matched_at=url,
                    severity=Severity.HIGH,
                    provider="tinja",
                    description=f"Engine: {engine}" if engine else "SSTI detected",
                    extra_data={
                        k: v for k, v in data.items() if k not in ("url", "URL")
                    },
                )
            )

        return results
