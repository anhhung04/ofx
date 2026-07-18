"""whois — domain WHOIS registration lookup."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import Task
from ofx.tasks.output_types import Domain
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("whois")
class WhoisTask(Task):
    name = "whois"
    cmd = "whois"
    description = "Domain WHOIS registration lookup"
    category = "domain/info"
    install_cmd = "apt install -y whois"
    output_types = [Domain]

    opts = {}

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = []

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Domain]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        def _first_match(pattern: str) -> str:
            m = re.search(pattern, raw, re.IGNORECASE | re.MULTILINE)
            return m.group(1).strip() if m else ""

        domain_name = _first_match(r"^Domain Name:\s*(.+)$")
        registrar = _first_match(r"^Registrar:\s*(.+)$")
        creation_date = _first_match(r"^Creation Date:\s*(.+)$")
        expiration_date = _first_match(
            r"^Registr(?:y|ar) Expir(?:y|ation) Date:\s*(.+)$"
        )

        name_servers: list[str] = []
        for m in re.finditer(
            r"^Name Server:\s*(.+)$", raw, re.IGNORECASE | re.MULTILINE
        ):
            ns = m.group(1).strip()
            if ns:
                name_servers.append(ns.lower())

        if not domain_name and not registrar:
            return []

        return [
            Domain(
                domain=domain_name.lower() if domain_name else "",
                registrar=registrar,
                alive=True,
                creation_date=creation_date,
                expiration_date=expiration_date,
                extra_data={"name_servers": name_servers},
            )
        ]
