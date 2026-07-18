"""tplmap — Server-Side Template Injection exploitation tool."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry

_CONFIRMED_RE = re.compile(
    r"(?:Confirmed|Tplmap identified|injection point found)",
    re.IGNORECASE,
)
_ENGINE_RE = re.compile(
    r"(?:engine|template\s*engine|identified)\s*[:\-]?\s*(\S+)",
    re.IGNORECASE,
)
_INJECTABLE_RE = re.compile(
    r"(?:parameter|inject)\s*['\"]?(\S+?)['\"]?\s*(?:is|appears)\s*(?:injectable|vulnerable)",
    re.IGNORECASE,
)

@TaskRegistry.register("tplmap")
class TplmapTask(Task):
    name = "tplmap"
    cmd = "tplmap"
    description = "Server-Side Template Injection exploitation tool"
    category = "vuln/injection"
    install_cmd = "uv tool install tplmap"
    output_types = [Vulnerability]

    opts = {
        "data": OptDef(flag="-d", type=str, help="POST data string"),
        "cookie": OptDef(flag="-c", type=str, help="HTTP cookies"),
        "headers": OptDef(flag="-H", type=str, help="Custom HTTP headers"),
        "method": OptDef(flag="-X", type=str, help="HTTP method"),
        "level": OptDef(flag="--level", type=int, help="Level of tests (1-5)"),
        "technique": OptDef(flag="-t", type=str, help="Injection technique"),
        "proxy": OptDef(flag="--proxy", type=str, help="Proxy URL"),
        "os_shell": OptDef(flag="--os-shell", is_flag=True, help="Spawn OS shell"),
        "os_cmd": OptDef(flag="--os-cmd", type=str, help="Execute OS command"),
    }

    input_flag = "-u"
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[Vulnerability] = []
        engine = ""
        param = ""

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            m_engine = _ENGINE_RE.search(line)
            if m_engine:
                engine = m_engine.group(1)

            m_param = _INJECTABLE_RE.search(line)
            if m_param:
                param = m_param.group(1)

            if _CONFIRMED_RE.search(line):
                desc = f"Engine: {engine}" if engine else "SSTI confirmed"
                results.append(
                    Vulnerability(
                        name="Server-Side Template Injection",
                        matched_at=param or "unknown",
                        severity=Severity.HIGH,
                        provider="tplmap",
                        description=desc,
                        extra_data={"engine": engine} if engine else {},
                    )
                )

        return results
