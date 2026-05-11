"""coercer — Windows authentication coercion scanner (PetitPotam, PrinterBug, etc.)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("coercer")
class CoercerTask(Task):
    name = "coercer"
    cmd = "coercer"
    description = (
        "Windows authentication coercion scanner (PetitPotam, PrinterBug, DFSCoerce)"
    )
    category = "ad/coerce"
    install_cmd = "uv tool install coercer"
    output_types = [Vulnerability, Tag]

    opts = {
        "username": OptDef(flag="-u", type=str, help="Username"),
        "password": OptDef(flag="-p", type=str, help="Password"),
        "hash": OptDef(flag="--hashes", type=str, help="NTLM hashes"),
        "domain": OptDef(flag="-d", type=str, help="Domain"),
        "listener": OptDef(flag="-l", type=str, help="Listener IP (attacker)"),
        "target_file": OptDef(
            flag="--targets-file", type=str, help="File with target IPs"
        ),
        "filter_protocol": OptDef(
            flag="--filter-protocol-name",
            type=str,
            help="Filter by protocol (MS-EFSR, MS-RPRN, etc.)",
        ),
        "filter_method": OptDef(
            flag="--filter-method-name", type=str, help="Filter by method name"
        ),
        "always_continue": OptDef(
            flag="--always-continue",
            is_flag=True,
            help="Continue after successful coercion",
        ),
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose output"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags: list[str] = []

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``coercer scan -t target -l listener [options]``."""
        mode = kwargs.pop("mode", "scan")
        listener = kwargs.pop("listener", "")

        parts: list[str] = [self.cmd, mode, "-t", self._q(target)]

        if listener:
            parts.extend(["-l", self._q(listener)])

        parts.extend(self._build_opt_parts(kwargs, skip_keys=["mode", "listener"]))

        return " ".join(parts), None

    # [+] MS-EFSR (EfsRpcOpenFileRaw) on 10.0.0.1 -> VULNERABLE
    _VULN_RE = re.compile(r"\[\+\]\s*(\S+)\s*\((\S+)\)\s*on\s*(\S+)")
    # [-] MS-RPRN (RpcRemoteFindFirstPrinterChangeNotification) on 10.0.0.1 -> NOT VULNERABLE
    _SAFE_RE = re.compile(r"\[-\]\s*(\S+)\s*\((\S+)\)\s*on\s*(\S+)")

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Tag]:
        raw = stdout or ""
        results: list[Vulnerability | Tag] = []

        for line in raw.splitlines():
            line = line.strip()
            m = self._VULN_RE.search(line)
            if m:
                results.append(
                    Vulnerability(
                        name=f"Coercion: {m.group(1)}",
                        severity=Severity.HIGH,
                        description=f"{m.group(1)} via {m.group(2)} on {m.group(3)}",
                        provider="coercer",
                    )
                )

        return results
