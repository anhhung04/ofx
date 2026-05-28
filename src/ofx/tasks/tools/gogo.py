"""gogo — fast port scanner and fingerprint engine by chainreactors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Port, Tag, Url, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("gogo")
class GogoTask(Task):
    name = "gogo"
    cmd = "gogo"
    description = "Fast port scanner with fingerprinting and nuclei integration"
    category = "port/scan"
    install_cmd = (
        "GOBIN=$TOOLS_BIN_DIR go install -v github.com/chainreactors/gogo/v2@latest"
    )
    output_types = [Port, Url, Tag, Vulnerability]

    opts = {
        "ports": OptDef(
            flag="-p", type=str, help="Ports to scan (e.g. top2,win,db,1-1000)"
        ),
        "mod": OptDef(flag="-m", type=str, help="Smart mode (s/ss/sc/default)"),
        "threads": OptDef(flag="-t", type=int, help="Concurrent threads"),
        "timeout": OptDef(flag="-d", type=int, help="Socket/HTTP timeout in seconds"),
        "ssl_timeout": OptDef(flag="-D", type=int, help="SSL/HTTPS timeout in seconds"),
        "exploit": OptDef(flag="-e", is_flag=True, help="Enable nuclei exploit scan"),
        "verbose": OptDef(
            flag="-v", is_flag=True, help="Enable active fingerprint scan"
        ),
        "spray": OptDef(
            flag="-s", is_flag=True, help="Enable port-first spray generator"
        ),
        "ping": OptDef(flag="--ping", is_flag=True, help="Pre-scan with ping"),
        "workflow": OptDef(flag="-w", type=str, help="Use a built-in workflow preset"),
        "exploit_name": OptDef(
            flag="-E", type=str, help="Specify nuclei template name"
        ),
        "suffix": OptDef(flag="--suffix", type=str, help="URL path suffix"),
        "extract": OptDef(flag="--extract", type=str, help="Custom extract regex"),
        "proxy": OptDef(flag="--proxy", type=str, help="SOCKS5 proxy URL"),
    }

    input_flag = "-i"
    file_flag = "-l"
    output_flag = "-f"
    silent_flag = "-q"
    extra_flags = ["-C", "-O", "jsonlines"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build gogo command.

        Overrides base to insert -O jsonlines before the output flag and
        to handle the workflow option (which replaces -i target).
        """
        if not target:
            raise ValueError(f"Task '{self.name}' requires a non-empty target")

        parts: list[str] = [self.cmd]

        wf = kwargs.pop("workflow", None)

        parts.extend(self._build_opt_parts(kwargs))

        # Quiet mode + uncompressed jsonlines output
        parts.extend(["-q", "-C", "-O", "jsonlines"])

        output_file = self._make_output_path()
        parts.extend([self.output_flag, str(output_file)])

        if wf:
            parts.extend(["-w", self._q(wf)])
            # Workflow already defines target, but -i overrides
            if target:
                parts.extend([self.input_flag, self._q(target)])
        else:
            target_is_file = (
                target and not target.startswith("http") and Path(target).is_file()
            )
            if target_is_file:
                parts.extend([self.file_flag, self._q(target)])
            else:
                parts.extend([self.input_flag, self._q(target)])

        return " ".join(parts), output_file

    def parse_line(self, line: str) -> list[Port | Url | Tag | Vulnerability]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        return self._parse_entry(data)

    def _parse_entry(self, data: dict) -> list[Port | Url | Tag | Vulnerability]:
        """Parse a single gogo JSON entry into typed outputs."""
        results: list[Port | Url | Tag | Vulnerability] = []

        ip = data.get("ip", "")
        host = data.get("host", ip)
        port = self._safe_int(data.get("port", 0))
        protocol = data.get("protocol", "tcp")

        if not ip and not host:
            return []

        # Port result
        if port:
            frameworks = data.get("frameworks", [])
            service = ""
            if frameworks:
                service = (
                    frameworks[0].get("name", "")
                    if isinstance(frameworks[0], dict)
                    else str(frameworks[0])
                )
            results.append(
                Port(
                    port=port,
                    ip=ip,
                    host=host,
                    state="open",
                    protocol=protocol,
                    service_name=service,
                )
            )

        # URL result (if HTTP)
        url = data.get("url", "")
        status_code = self._safe_int(data.get("status", 0))
        title = data.get("title", "")
        if url or (protocol in ("http", "https") and port):
            if not url:
                scheme = (
                    "https" if protocol == "https" or port in (443, 8443) else "http"
                )
                url = f"{scheme}://{host or ip}:{port}"
            results.append(
                Url(
                    url=url,
                    host=host or ip,
                    status_code=status_code,
                    title=title,
                )
            )

        # Tags from frameworks/fingerprints
        frameworks = data.get("frameworks", [])
        for fw in frameworks:
            name = fw.get("name", "") if isinstance(fw, dict) else str(fw)
            if name:
                results.append(
                    Tag(
                        name=name,
                        value=url or f"{ip}:{port}",
                        category="fingerprint",
                    )
                )

        # Vulnerabilities from nuclei results
        for vuln in data.get("vulns", []):
            vuln_name = (
                vuln if isinstance(vuln, str) else vuln.get("name", vuln.get("id", ""))
            )
            if vuln_name:
                severity_str = (
                    vuln.get("severity", "info") if isinstance(vuln, dict) else "info"
                )
                from ofx.tasks.output_types import Severity

                sev_map = {
                    "critical": Severity.CRITICAL,
                    "high": Severity.HIGH,
                    "medium": Severity.MEDIUM,
                    "low": Severity.LOW,
                }
                results.append(
                    Vulnerability(
                        name=vuln_name,
                        matched_at=url or f"{ip}:{port}",
                        severity=sev_map.get(severity_str.lower(), Severity.INFO),
                        provider="gogo/nuclei",
                    )
                )

        return results
