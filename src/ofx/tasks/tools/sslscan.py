"""sslscan — SSL/TLS configuration and cipher scanner."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Certificate, Severity, Vulnerability
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("sslscan")
class SslscanTask(Task):
    name = "sslscan"
    cmd = "sslscan"
    description = "SSL/TLS configuration and cipher scanner"
    category = "ssl/scan"
    install_cmd = "apt install -y sslscan"
    output_types = [Certificate, Vulnerability]

    opts = {
        "show_certificate": OptDef(
            flag="--show-certificate",
            is_flag=True,
            help="Show full certificate details",
        ),
        "no_check_certificate": OptDef(
            flag="--no-check-certificate",
            is_flag=True,
            help="Don't check certificate validity",
        ),
        "starttls": OptDef(
            flag="--starttls",
            type=str,
            help="STARTTLS protocol: ftp,imap,irc,ldap,pop3,smtp,mysql,xmpp,psql",
        ),
        "ssl2": OptDef(flag="--ssl2", is_flag=True, help="Test SSLv2 ciphers"),
        "ssl3": OptDef(flag="--ssl3", is_flag=True, help="Test SSLv3 ciphers"),
        "tls10": OptDef(flag="--tls10", is_flag=True, help="Test TLS 1.0 ciphers"),
        "tls11": OptDef(flag="--tls11", is_flag=True, help="Test TLS 1.1 ciphers"),
        "tls12": OptDef(flag="--tls12", is_flag=True, help="Test TLS 1.2 ciphers"),
        "tls13": OptDef(flag="--tls13", is_flag=True, help="Test TLS 1.3 ciphers"),
        "targets": OptDef(flag="--targets", type=str, help="File containing targets"),
    }

    input_flag = None
    file_flag = None
    output_flag = "--xml"
    extra_flags = ["--no-colour"]

    def _output_suffix(self) -> str:
        return ".xml"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Override for ``--xml=FILE`` syntax and positional target."""
        parts: list[str] = [self.cmd, *self.extra_flags]

        parts.extend(self._build_opt_parts(kwargs))

        output_file: Path | None = None
        if self.output_flag:
            output_file = self._make_output_path()
            parts.append(f"{self.output_flag}={output_file}")

        parts.append(self._q(target))

        return " ".join(parts), output_file

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Certificate | Vulnerability]:
        xml_source = self._raw_output(
            stdout if "<document>" in stdout else "",
            output_file,
        )

        if not xml_source:
            return []

        try:
            root = ET.fromstring(xml_source)
        except ET.ParseError:
            return []

        results: list[Certificate | Vulnerability] = []

        for ssltest in root.findall(".//ssltest"):
            target = ssltest.get("host", "")
            port = ssltest.get("port", "")
            target_str = f"{target}:{port}" if port else target

            for cert_el in ssltest.findall(".//certificate"):
                subject = self._child_text(cert_el, "subject")
                issuer = self._child_text(cert_el, "issuer")
                not_before = self._child_text(cert_el, "not-valid-before")
                not_after = self._child_text(cert_el, "not-valid-after")
                self_signed_text = self._child_text(cert_el, "self-signed").lower()
                fingerprint = self._child_text(cert_el, "fingerprint")
                altnames = self._child_text(cert_el, "altnames")

                subject_cn = ""
                if subject:
                    for part in subject.split("/"):
                        if part.startswith("CN="):
                            subject_cn = part[3:]
                            break

                issuer_cn = ""
                if issuer:
                    for part in issuer.split("/"):
                        if part.startswith("CN="):
                            issuer_cn = part[3:]
                            break

                san_list = (
                    [s.strip() for s in altnames.split(",") if s.strip()]
                    if altnames
                    else []
                )

                if not subject_cn and not fingerprint:
                    continue

                results.append(
                    Certificate(
                        host=target_str,
                        fingerprint_sha256=fingerprint,
                        subject_cn=subject_cn,
                        subject_an=san_list,
                        issuer_cn=issuer_cn,
                        not_before=not_before,
                        not_after=not_after,
                        self_signed=self_signed_text in ("true", "1", "yes"),
                    )
                )

            for cipher_el in ssltest.findall(".//cipher"):
                status = cipher_el.get("status", "").lower()
                ssl_version = cipher_el.get("sslversion", "")
                cipher_name = cipher_el.get("cipher", "")
                bits = self._safe_int(cipher_el.get("bits"))

                if status in ("rejected", "failed"):
                    continue

                severity = Severity.INFO
                is_weak = False

                if "sslv2" in ssl_version.lower():
                    severity = Severity.HIGH
                    is_weak = True
                elif "sslv3" in ssl_version.lower():
                    severity = Severity.HIGH
                    is_weak = True
                elif bits and bits < 128:
                    severity = Severity.MEDIUM
                    is_weak = True
                elif "null" in cipher_name.lower():
                    severity = Severity.HIGH
                    is_weak = True
                elif "rc4" in cipher_name.lower():
                    severity = Severity.MEDIUM
                    is_weak = True
                elif "export" in cipher_name.lower():
                    severity = Severity.HIGH
                    is_weak = True

                if is_weak:
                    results.append(
                        Vulnerability(
                            name=f"Weak cipher: {cipher_name}",
                            matched_at=target_str,
                            severity=severity,
                            provider="sslscan",
                            description=(f"{ssl_version} {cipher_name} ({bits} bits)"),
                            extra_data={
                                "sslversion": ssl_version,
                                "cipher": cipher_name,
                                "bits": bits,
                            },
                        )
                    )

            for hb_el in ssltest.findall(".//heartbleed"):
                vuln_attr = hb_el.get("vulnerable", "").lower()
                if vuln_attr in ("1", "true", "yes"):
                    results.append(
                        Vulnerability(
                            name="Heartbleed",
                            matched_at=target_str,
                            severity=Severity.CRITICAL,
                            provider="sslscan",
                            description="Server is vulnerable to Heartbleed (CVE-2014-0160)",
                            tags=["heartbleed", "CVE-2014-0160"],
                        )
                    )

        return results

    @staticmethod
    def _child_text(parent: ET.Element, tag: str) -> str:
        """Return text content of a child element or empty string."""
        el = parent.find(tag)
        return (el.text or "").strip() if el is not None else ""
