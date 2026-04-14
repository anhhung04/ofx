"""theHarvester — email and subdomain harvesting tool."""

from __future__ import annotations

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain, UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("theharvester")
class TheHarvesterTask(Task):
    name = "theharvester"
    cmd = "theHarvester"
    description = "Email and subdomain harvesting from public sources"
    category = "osint/recon"
    install_cmd = "uv tool install theHarvester"
    output_types = [Subdomain, UserAccount]

    opts = {
        "source": OptDef(
            flag="-b",
            type=str,
            help="Source: all,bing,google,linkedin,etc",
        ),
        "limit": OptDef(flag="-l", type=int, help="Limit results"),
        "start": OptDef(flag="-S", type=int, help="Start result number"),
        "shodan": OptDef(flag="-s", is_flag=True, help="Use Shodan"),
        "dns_brute": OptDef(
            flag="-c", is_flag=True, help="DNS brute force"
        ),
        "virtual_host": OptDef(
            flag="-v", is_flag=True, help="Virtual host verification"
        ),
        "dns_lookup": OptDef(flag="-n", is_flag=True, help="DNS lookup"),
    }

    input_flag = "-d"
    file_flag = None
    output_flag = "-f"
    extra_flags = ["-b", "all"]

    def _output_suffix(self) -> str:
        return ".xml"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Override to replace default ``-b all`` when source opt is given."""
        base_flags = list(self.extra_flags)

        # If the user supplied a source, drop the default -b all
        if kwargs.get("source"):
            base_flags = []

        parts: list[str] = [self.cmd, *base_flags]

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

        output_file: Path | None = None
        if self.output_flag:
            _fd, _path = tempfile.mkstemp(
                prefix=f".ofx_task_{self.name}_",
                suffix=self._output_suffix(),
            )
            os.close(_fd)
            output_file = Path(_path)
            parts.extend([self.output_flag, str(output_file)])

        if self.input_flag:
            parts.extend([self.input_flag, target])
        else:
            parts.append(target)

        return " ".join(parts), output_file

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Subdomain | UserAccount]:
        results: list[Subdomain | UserAccount] = []

        # Try XML first (theharvester writes .xml with -f)
        xml_content = ""
        if output_file:
            xml_path = output_file.with_suffix(".xml")
            if xml_path.exists():
                xml_content = self._read_output_file(xml_path)
            elif output_file.exists():
                xml_content = self._read_output_file(output_file)

        if xml_content:
            results.extend(self._parse_xml(xml_content))
            if results:
                return results

        # Fallback: parse stdout
        if stdout:
            results.extend(self._parse_stdout(stdout))

        return results

    def _parse_xml(self, xml_source: str) -> list[Subdomain | UserAccount]:
        results: list[Subdomain | UserAccount] = []
        try:
            root = ET.fromstring(xml_source)
        except ET.ParseError:
            return results

        for email_el in root.iter("email"):
            email = (email_el.text or "").strip()
            if not email or "@" not in email:
                continue
            parts = email.split("@", 1)
            results.append(
                UserAccount(
                    username=parts[0],
                    domain=parts[1],
                    source="theharvester",
                )
            )

        for tag_name in ("host", "hostname"):
            for host_el in root.iter(tag_name):
                host = (host_el.text or "").strip()
                if not host:
                    continue
                # Strip trailing IP in format "host:ip"
                host = host.split(":")[0].strip()
                if host:
                    domain = (
                        ".".join(host.rsplit(".", 2)[-2:])
                        if "." in host
                        else host
                    )
                    results.append(Subdomain(host=host, domain=domain))

        return results

    def _parse_stdout(self, raw: str) -> list[Subdomain | UserAccount]:
        results: list[Subdomain | UserAccount] = []
        email_re = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
        seen: set[str] = set()

        for line in raw.splitlines():
            line = line.strip()
            for email in email_re.findall(line):
                if email in seen:
                    continue
                seen.add(email)
                parts = email.split("@", 1)
                results.append(
                    UserAccount(
                        username=parts[0],
                        domain=parts[1],
                        source="theharvester",
                    )
                )

        return results
