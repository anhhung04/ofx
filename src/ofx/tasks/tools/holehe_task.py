"""holehe — email OSINT account checker across websites."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import UserAccount
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("holehe")
class HoleheTask(Task):
    name = "holehe"
    cmd = "holehe"
    description = "Email OSINT account existence checker"
    category = "user/recon/email"
    install_cmd = "uv tool install holehe"
    output_types = [UserAccount]

    opts = {
        "only_used": OptDef(
            flag="--only-used",
            is_flag=True,
            help="Show only used accounts",
        ),
        "timeout": OptDef(flag="-t", type=int, help="Request timeout"),
    }

    input_flag = None  # positional
    file_flag = None
    output_flag = None
    extra_flags = ["--no-color"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Override for positional email target."""
        parts: list[str] = [self.cmd, *self.extra_flags]

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
            output_file = self._make_output_path()
            parts.extend([self.output_flag, str(output_file)])

        parts.append(target)

        return " ".join(parts), output_file

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[UserAccount]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[UserAccount] = []
        # holehe lines: [+] email is used on: SiteName
        used_re = re.compile(
            r"\[\+\]\s*(\S+@\S+)\s+is used on:\s*(.+)", re.IGNORECASE
        )
        # Alternative format: [+] SiteName
        alt_re = re.compile(r"\[\+\]\s+(.+)")

        email = ""
        for line in raw.splitlines():
            line = line.strip()

            m = used_re.match(line)
            if m:
                email = m.group(1).strip()
                site = m.group(2).strip()
                results.append(
                    UserAccount(
                        username=email,
                        source=site,
                        comment="Account exists",
                    )
                )
                continue

            # Some holehe versions list sites after the email header
            if not email:
                # Try to find email from a header line
                email_match = re.search(r"([\w.+-]+@[\w.-]+\.\w+)", line)
                if email_match:
                    email = email_match.group(1)
                continue

            m_alt = alt_re.match(line)
            if m_alt and email:
                site = m_alt.group(1).strip()
                if site and not site.startswith("["):
                    results.append(
                        UserAccount(
                            username=email,
                            source=site,
                            comment="Account exists",
                        )
                    )

        return results
