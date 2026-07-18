"""gobuster — directory/DNS/vhost brute-forcing tool."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("gobuster")
class GobusterTask(Task):
    name = "gobuster"
    cmd = "gobuster"
    description = "Directory/DNS/vhost brute-forcing tool"
    category = "url/fuzz"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/OJ/gobuster/v3@latest"
    output_types = [Url]

    opts = {
        "mode": OptDef(flag="--mode", type=str, help="Gobuster mode (dir/dns/vhost)"),
        "threads": OptDef(flag="-t", type=int, help="Number of concurrent threads"),
        "wordlist": OptDef(flag="-w", type=str, help="Path to wordlist"),
        "status_codes": OptDef(
            flag="-s", type=str, help="Positive status codes (e.g. 200,204,301)"
        ),
        "extensions": OptDef(
            flag="-x", type=str, help="File extensions to search (e.g. php,html)"
        ),
        "timeout": OptDef(flag="--timeout", type=int, help="HTTP timeout in seconds"),
        "follow_redirect": OptDef(flag="-r", is_flag=True, help="Follow redirects"),
        "cookies": OptDef(flag="-c", type=str, help="Cookies to use"),
        "headers": OptDef(flag="-H", type=str, help="HTTP header(s)"),
        "method": OptDef(flag="-m", type=str, help="HTTP method"),
        "proxy": OptDef(flag="--proxy", type=str, help="Proxy URL"),
        "no_tls_validation": OptDef(
            flag="-k", is_flag=True, help="Skip TLS certificate verification"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = "-o"
    silent_flag = "-q"
    extra_flags = ["--no-progress", "--no-color"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Prepend mode subcommand and use ``-u`` for target."""
        mode = kwargs.pop("mode", "dir")
        parts: list[str] = [self.cmd, mode, *self.extra_flags]
        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        has_status_codes = False
        for key, value in kwargs.items():
            if key.startswith("_"):
                continue
            opt = self.opts.get(key)
            if opt is None or key == "mode":
                continue
            if opt.is_flag:
                if value:
                    parts.append(opt.flag)
            elif value is not None:
                parts.extend([opt.flag, self._q(value)])
                if key == "status_codes":
                    has_status_codes = True

        if has_status_codes:
            parts.extend(["-b", self._q("")])

        output_file: Path | None = None
        if self.output_flag:
            output_file = self._make_output_path()
            parts.extend([self.output_flag, str(output_file)])

        parts.extend(["-u", self._q(target)])

        return " ".join(parts), output_file

    _LINE_RE = re.compile(r"^(/\S*)\s+\(Status:\s*(\d+)\)\s+\[Size:\s*(\d+)\]")

    def parse_line(self, line: str) -> list[Url]:
        line = line.strip()
        if not line:
            return []
        m = self._LINE_RE.match(line)
        if not m:
            return []
        return [
            Url(
                url=m.group(1),
                status_code=self._safe_int(m.group(2)),
                content_length=self._safe_int(m.group(3)),
            )
        ]
