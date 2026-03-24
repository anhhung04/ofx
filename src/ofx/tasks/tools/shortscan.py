"""shortscan — IIS shortname vulnerability scanner."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Url, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("shortscan")
class ShortscanTask(Task):
    name = "shortscan"
    cmd = "shortscan"
    description = "IIS shortname vulnerability scanner"
    category = "web/fuzz"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v github.com/bitquark/shortscan/cmd/shortscan@latest"
    )
    output_types = [Url, Vulnerability]

    opts = {
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "timeout": OptDef(flag="--timeout", type=int, help="Request timeout in seconds"),
        "wordlist": OptDef(
            flag="-w", type=str, help="Wordlist for full name matching"
        ),
        "header": OptDef(flag="-H", type=str, help="Custom header (key:value)"),
        "no_recurse": OptDef(
            flag="--no-recurse", is_flag=True, help="Disable recursive scanning"
        ),
        "full_url": OptDef(
            flag="--full-url", is_flag=True, help="Show full URLs in output"
        ),
        "patience": OptDef(
            flag="-p", type=int, help="Patience level (0-2)"
        ),
    }

    input_flag = None  # positional URL
    file_flag = None
    output_flag = None
    extra_flags = []

    def _output_suffix(self) -> str:
        return ".txt"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url | Vulnerability]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[Url | Vulnerability] = []
        found_shortnames: list[str] = []

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Match shortname discoveries — lines with short filenames (e.g. "ASPNET~1.DLL")
            shortname_match = re.search(
                r"(?:^|\s)([A-Z0-9_~]+\.[A-Z0-9]{1,3})\b", line, re.IGNORECASE
            )
            if shortname_match and "~" in shortname_match.group(1):
                name = shortname_match.group(1)
                found_shortnames.append(name)
                results.append(
                    Url(
                        url=name,
                        extra_data={"shortname": name, "raw_line": line},
                    )
                )

            # Match full URL paths
            url_match = re.search(r"(https?://\S+)", line, re.IGNORECASE)
            if url_match:
                results.append(Url(url=url_match.group(1)))

        # If any shortnames found, report vulnerability
        if found_shortnames:
            results.append(
                Vulnerability(
                    name="IIS Short Name Disclosure",
                    id="iis-shortname",
                    severity=Severity.MEDIUM,
                    provider="shortscan",
                    description=f"Found {len(found_shortnames)} short names: {', '.join(found_shortnames[:10])}",
                    tags=["iis", "shortname", "information-disclosure"],
                )
            )

        return results
