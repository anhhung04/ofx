"""hashid — hash identifier tool."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("hashid")
class HashidTask(Task):
    name = "hashid"
    cmd = "hashid"
    description = "Hash identifier tool"
    category = "crypto/identify"
    install_cmd = "uv tool install hashid"
    output_types = [Tag]

    opts = {
        "file": OptDef(flag="-f", type=str, help="File containing hashes"),
    }

    input_flag = None
    file_flag = "-f"
    output_flag = None
    json_flag = "-j"
    extra_flags = ["-m"]

    def _output_suffix(self) -> str:
        return ".json"

    # [+] MD5 [Hashcat Mode: 0] [JtR Format: raw-md5]
    _TYPE_RE = re.compile(
        r"\[\+\]\s+(.+?)(?:\s+\[Hashcat Mode:\s*(\d+)\])?(?:\s+\[JtR Format:\s*(\S+)\])?"
    )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[Tag] = []
        current_hash = ""

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Lines like "Analyzing 'hash_value'"
            if line.startswith("Analyzing"):
                m = re.search(r"'([^']+)'", line)
                if m:
                    current_hash = m.group(1)
                continue

            m = self._TYPE_RE.match(line)
            if m:
                type_name = m.group(1).strip()
                results.append(
                    Tag(
                        name="hash_type",
                        value=type_name,
                        match=current_hash,
                        category="crypto",
                    )
                )

        return results
