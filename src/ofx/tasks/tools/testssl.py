"""testssl.sh — TLS/SSL cipher and vulnerability scanner."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Certificate, Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_SEVERITY_MAP = {
    "ok": Severity.INFO,
    "info": Severity.INFO,
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
    "critical": Severity.CRITICAL,
}


@TaskRegistry.register("testssl")
class TestsslTask(Task):
    name = "testssl"
    cmd = "testssl.sh"
    description = "TLS/SSL configuration and vulnerability scanner"
    category = "dns/recon/tls"
    install_cmd = (
        "git clone --depth 1 https://github.com/drwetter/testssl.sh.git"
        " $TOOLS_DIR/testssl && ln -sf $TOOLS_DIR/testssl/testssl.sh $TOOLS_BIN_DIR/testssl.sh"
    )
    output_types = [Certificate, Vulnerability, Tag]

    opts = {
        "protocols": OptDef(flag="-p", is_flag=True, help="Check protocols"),
        "ciphers": OptDef(flag="-E", is_flag=True, help="Check ciphers"),
        "vulnerabilities": OptDef(
            flag="-U", is_flag=True, help="Check vulnerabilities"
        ),
        "server_defaults": OptDef(
            flag="-S",
            is_flag=True,
            help="Display server default picks and certificate info",
        ),
        "headers": OptDef(flag="-h", is_flag=True, help="Check HTTP headers"),
        "starttls": OptDef(
            flag="--starttls",
            type=str,
            help="Protocol for STARTTLS: ftp/smtp/pop3/imap/xmpp/telnet/ldap",
        ),
        "openssl": OptDef(flag="--openssl", type=str, help="Path to openssl binary"),
        "full": OptDef(flag="--full", is_flag=True, help="Full test"),
    }

    input_flag = None  # positional host:port
    file_flag = "--file"
    output_flag = "--jsonfile"
    extra_flags = ["--color", "0"]
    silent_flag = "--quiet"

    def _output_suffix(self) -> str:
        return ".json"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Certificate | Vulnerability | Tag]:
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        if not isinstance(data, list):
            return []

        results: list[Certificate | Vulnerability | Tag] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue

            entry_id = entry.get("id", "")
            finding = entry.get("finding", "")
            severity_str = entry.get("severity", "").lower()
            ip = entry.get("ip", "")
            port = entry.get("port", "")
            target = f"{ip}:{port}" if ip and port else ip

            if not entry_id or not target:
                continue

            severity = _SEVERITY_MAP.get(severity_str, Severity.UNKNOWN)

            if entry_id.startswith("cert_"):
                results.append(
                    Certificate(
                        host=target,
                        subject_cn=finding,
                        extra_data={
                            "id": entry_id,
                            "severity": severity_str,
                            "ip": ip,
                            "port": port,
                        },
                    )
                )
            elif "vuln" in entry_id.lower() or severity in (
                Severity.MEDIUM,
                Severity.HIGH,
                Severity.CRITICAL,
            ):
                results.append(
                    Vulnerability(
                        name=entry_id,
                        id=entry_id,
                        matched_at=target,
                        severity=severity,
                        provider="testssl",
                        description=finding,
                    )
                )
            else:
                results.append(
                    Tag(
                        name=entry_id,
                        value=finding,
                        match=target,
                        category="tls",
                    )
                )

        return results
