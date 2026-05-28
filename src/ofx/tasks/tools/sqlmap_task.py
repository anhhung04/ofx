"""sqlmap — automatic SQL injection detection and exploitation."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("sqlmap")
class SqlmapTask(Task):
    name = "sqlmap"
    cmd = "sqlmap"
    description = "Automatic SQL injection detection and exploitation tool"
    category = "vuln/scan/sqli"
    install_cmd = "uv tool install sqlmap"
    output_types = [Vulnerability]

    opts = {
        "data": OptDef(flag="--data", type=str, help="POST data string"),
        "cookie": OptDef(flag="--cookie", type=str, help="HTTP cookie header"),
        "headers": OptDef(flag="-H", type=str, help="Extra HTTP header"),
        "method": OptDef(flag="--method", type=str, help="HTTP method to use"),
        "level": OptDef(flag="--level", type=int, help="Level of tests (1-5)"),
        "risk": OptDef(flag="--risk", type=int, help="Risk of tests (1-3)"),
        "threads": OptDef(flag="--threads", type=int, help="Number of threads"),
        "technique": OptDef(
            flag="--technique", type=str, help="SQL injection techniques BEUSTQ"
        ),
        "tamper": OptDef(flag="--tamper", type=str, help="Tamper script(s)"),
        "dbms": OptDef(flag="--dbms", type=str, help="Force DBMS type"),
        "os": OptDef(flag="--os", type=str, help="Force OS type"),
        "proxy": OptDef(flag="--proxy", type=str, help="HTTP proxy"),
        "tor": OptDef(flag="--tor", is_flag=True, help="Use Tor network"),
        "random_agent": OptDef(
            flag="--random-agent", is_flag=True, help="Use random User-Agent"
        ),
        "forms": OptDef(flag="--forms", is_flag=True, help="Parse and test forms"),
        "crawl": OptDef(flag="--crawl", type=int, help="Crawl depth"),
        "dump": OptDef(flag="--dump", is_flag=True, help="Dump DBMS table entries"),
        "dbs": OptDef(flag="--dbs", is_flag=True, help="Enumerate databases"),
        "tables": OptDef(flag="--tables", is_flag=True, help="Enumerate tables"),
    }

    input_flag = "-u"
    file_flag = None
    output_flag = None
    extra_flags = ["--batch", "--flush-session"]

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

        # Extract target URL from sqlmap output
        target_url = ""
        target_match = re.search(r"(?:testing URL|URL)\s*['\"]?(https?://\S+)", raw)
        if target_match:
            target_url = target_match.group(1).rstrip("'\"")

        # Split on separator lines to find individual findings
        current_param = ""
        current_type = ""
        current_title = ""
        current_payload = ""
        in_finding = False

        for line in raw.splitlines():
            line = line.strip()

            param_match = re.match(r"Parameter:\s*(.+)", line)
            if param_match:
                current_param = param_match.group(1).strip()
                in_finding = True
                continue

            if in_finding:
                type_match = re.match(r"Type:\s*(.+)", line)
                if type_match:
                    current_type = type_match.group(1).strip()
                    continue

                title_match = re.match(r"Title:\s*(.+)", line)
                if title_match:
                    current_title = title_match.group(1).strip()
                    continue

                payload_match = re.match(r"Payload:\s*(.+)", line)
                if payload_match:
                    current_payload = payload_match.group(1).strip()
                    continue

                if line == "---" or (line == "" and current_title):
                    if current_title:
                        results.append(
                            Vulnerability(
                                name=current_title,
                                matched_at=target_url or current_param,
                                severity=Severity.HIGH,
                                provider="sqlmap",
                                description=(
                                    f"Parameter: {current_param}, Type: {current_type}"
                                ),
                                tags=["sqli"],
                                extra_data={
                                    "parameter": current_param,
                                    "type": current_type,
                                    "payload": current_payload,
                                },
                            )
                        )
                    current_type = ""
                    current_title = ""
                    current_payload = ""

        # Catch last finding if no trailing separator
        if current_title:
            results.append(
                Vulnerability(
                    name=current_title,
                    matched_at=target_url or current_param,
                    severity=Severity.HIGH,
                    provider="sqlmap",
                    description=(f"Parameter: {current_param}, Type: {current_type}"),
                    tags=["sqli"],
                    extra_data={
                        "parameter": current_param,
                        "type": current_type,
                        "payload": current_payload,
                    },
                )
            )

        return results
