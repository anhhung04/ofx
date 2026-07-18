"""amass — OWASP subdomain enumeration engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("amass")
class AmassTask(Task):
    name = "amass"
    cmd = "amass"
    description = "OWASP subdomain enumeration engine"
    category = "dns/recon"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/owasp-amass/amass/v5/...@latest"
    output_types = [Subdomain]

    success_codes: list[int] = [0, 1, 2]

    opts = {
        "active": OptDef(
            flag="-active", is_flag=True, help="Enable active recon methods"
        ),
        "brute": OptDef(
            flag="-brute", is_flag=True, help="Enable brute force subdomain guessing"
        ),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in minutes"),
        "sources": OptDef(flag="-src", type=str, help="Data source filter"),
        "max_dns_queries": OptDef(
            flag="-max-dns-queries", type=int, help="Maximum concurrent DNS queries"
        ),
    }

    input_flag = "-d"
    file_flag = "-df"
    output_flag = None

    def _output_suffix(self) -> str:
        return ".txt"

    def _legacy_enum_parts(
        self,
        target_parts: list[str],
        output_file: Path,
        *,
        active: bool,
        brute: bool,
        timeout: int | None,
        sources: str | None,
        max_dns_queries: int | None,
    ) -> list[str]:
        """Build the Amass v3/v4-style enum invocation."""
        parts: list[str] = [self.cmd, "enum"]
        parts.append("-active" if active else "-passive")
        parts.append("-silent")

        if brute:
            parts.append("-brute")
        if timeout is not None:
            parts.extend(["-timeout", self._q(timeout)])
        if sources:
            parts.extend(["-src", self._q(sources)])
        if max_dns_queries is not None:
            parts.extend(["-max-dns-queries", self._q(max_dns_queries)])

        parts.extend(["-o", self._q(output_file)])
        parts.extend(target_parts)
        return parts

    def _v5_enum_parts(
        self,
        target_parts: list[str],
        *,
        active: bool,
        brute: bool,
        timeout: int | None,
        sources: str | None,
    ) -> list[str]:
        """Build the Amass v5 enum invocation using a temp graph directory."""
        parts: list[str] = [self.cmd, "enum"]
        if active:
            parts.append("-active")
        if brute:
            parts.append("-brute")
        if timeout is not None:
            parts.extend(["-timeout", self._q(timeout)])
        if sources:
            parts.extend(["-include", self._q(sources)])

        parts.extend(["-dir", '"$tmpdir"'])
        parts.extend(target_parts)
        return parts

    def _v5_subs_parts(
        self,
        target_parts: list[str],
        output_file: Path,
    ) -> list[str]:
        """Build the Amass v5 subs invocation that exports discovered names."""
        return [
            self.cmd,
            "subs",
            "-silent",
            "-names",
            "-o",
            self._q(output_file),
            "-dir",
            '"$tmpdir"',
            *target_parts,
        ]

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build a compatibility command for both legacy and v5 Amass CLIs."""
        if not target:
            raise ValueError(f"Task '{self.name}' requires a non-empty target")

        active = bool(kwargs.pop("active", False))
        brute = bool(kwargs.pop("brute", False))
        timeout = kwargs.pop("timeout", None)
        sources = kwargs.pop("sources", None)
        max_dns_queries = kwargs.pop("max_dns_queries", None)

        target_parts = self._target_parts(target)
        output_file = self._make_output_path()

        legacy_cmd = " ".join(
            self._legacy_enum_parts(
                target_parts,
                output_file,
                active=active,
                brute=brute,
                timeout=timeout,
                sources=sources,
                max_dns_queries=max_dns_queries,
            )
        )
        v5_enum_cmd = " ".join(
            self._v5_enum_parts(
                target_parts,
                active=active,
                brute=brute,
                timeout=timeout,
                sources=sources,
            )
        )
        v5_subs_cmd = " ".join(self._v5_subs_parts(target_parts, output_file))

        command = (
            'if amass -version 2>&1 | grep -qE "v5\\."; then '
            'tmpdir=$(mktemp -d) && '
            'cleanup() { rm -rf "$tmpdir"; } && '
            'trap cleanup EXIT && '
            f"{v5_enum_cmd} >/dev/null && "
            f"{v5_subs_cmd}; "
            f"else {legacy_cmd}; fi"
        )
        return command, output_file

    def parse_line(self, line: str) -> list[Subdomain]:
        host = line.strip()
        if not host or host.startswith("#"):
            return []

        domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host

        return [Subdomain(host=host, domain=domain)]
