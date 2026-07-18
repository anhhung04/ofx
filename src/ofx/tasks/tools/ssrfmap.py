"""ssrfmap — SSRF exploitation tool."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Url, Vulnerability
from ofx.tasks.registry import TaskRegistry

_SSRF_RE = re.compile(
    r"(?:SSRF|found|exploitable|success|vulnerable)",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"(https?://[^\s\"'<>]+)")

@TaskRegistry.register("ssrfmap")
class SSRFmapTask(Task):
    name = "ssrfmap"
    cmd = "ssrfmap"
    description = "SSRF exploitation tool"
    category = "vuln/injection"
    install_cmd = "uv tool install SSRFmap"
    output_types = [Vulnerability, Url]

    opts = {
        "data": OptDef(flag="-d", type=str, help="POST data"),
        "cookie": OptDef(flag="-c", type=str, help="HTTP cookies"),
        "headers": OptDef(flag="-H", type=str, help="Custom HTTP headers"),
        "method": OptDef(flag="-m", type=str, help="HTTP method"),
        "modules": OptDef(flag="--modules", type=str, help="SSRF modules to use"),
        "proxy": OptDef(flag="--proxy", type=str, help="Proxy URL"),
        "lhost": OptDef(flag="--lhost", type=str, help="Local host for callbacks"),
        "lport": OptDef(flag="--lport", type=int, help="Local port for callbacks"),
    }

    input_flag = "-r"
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Target can be a request file (-r) or a URL (-u)."""
        parts: list[str] = [self.cmd, *self.extra_flags]

        parts.extend(self._build_opt_parts(kwargs))

        if target:
            if not target.startswith("http") and Path(target).is_file():
                parts.extend(["-r", self._q(target)])
            else:
                parts.extend(["-u", self._q(target)])

        return " ".join(parts), None

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Url]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[Vulnerability | Url] = []
        seen_urls: set[str] = set()

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            for m_url in _URL_RE.finditer(line):
                url = m_url.group(1)
                if url not in seen_urls:
                    seen_urls.add(url)
                    results.append(Url(url=url))

            if _SSRF_RE.search(line):
                results.append(
                    Vulnerability(
                        name="SSRF",
                        matched_at=line[:120],
                        severity=Severity.HIGH,
                        provider="ssrfmap",
                        description=line,
                    )
                )

        return results
