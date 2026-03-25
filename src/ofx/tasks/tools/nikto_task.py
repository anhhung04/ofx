"""nikto — web server vulnerability scanner."""

from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("nikto")
class NiktoTask(Task):
    name = "nikto"
    cmd = "nikto"
    description = "Web server vulnerability scanner"
    category = "vuln/scan/web"
    install_cmd = "apt install -y nikto"
    output_types = [Vulnerability]

    opts = {
        "port": OptDef(flag="-p", type=str, help="Port(s) to scan"),
        "ssl": OptDef(flag="-ssl", is_flag=True, help="Force SSL mode"),
        "plugins": OptDef(flag="-Plugins", type=str, help="Plugins to run"),
        "tuning": OptDef(
            flag="-Tuning", type=str, help="Scan tuning options"
        ),
        "timeout": OptDef(
            flag="-timeout", type=int, help="Timeout per request"
        ),
        "maxtime": OptDef(
            flag="-maxtime", type=int, help="Maximum scan time in seconds"
        ),
        "useragent": OptDef(
            flag="-useragent", type=str, help="Custom User-Agent string"
        ),
        "proxy": OptDef(flag="-useproxy", type=str, help="HTTP proxy to use"),
        "no_cache": OptDef(
            flag="-nocache", is_flag=True, help="Disable response caching"
        ),
    }

    input_flag = "-host"
    file_flag = None
    output_flag = "-o"
    extra_flags = ["-Format", "json", "-nointeractive"]

    def _output_suffix(self) -> str:
        return ".json"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        results: list[Vulnerability] = []

        # nikto JSON may be a single object or a list
        entries = data if isinstance(data, list) else [data]

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            host = entry.get("host", "")
            ip = entry.get("ip", "")
            port = entry.get("port", "")
            target = f"{host or ip}:{port}" if port else (host or ip)

            for vuln in entry.get("vulnerabilities", []):
                if not isinstance(vuln, dict):
                    continue

                osvdb = vuln.get("OSVDB", "")
                vuln_id = vuln.get("id", "")
                msg = vuln.get("msg", "")
                url = vuln.get("url", "")
                method = vuln.get("method", "")

                results.append(
                    Vulnerability(
                        name=msg or f"nikto-{vuln_id}",
                        id=str(osvdb) if osvdb else str(vuln_id),
                        matched_at=url or target,
                        severity=Severity.INFO,
                        provider="nikto",
                        description=msg,
                        extra_data={
                            "method": method,
                            "osvdb": osvdb,
                            "host": host,
                            "ip": ip,
                            "port": port,
                        },
                    )
                )

        return results
