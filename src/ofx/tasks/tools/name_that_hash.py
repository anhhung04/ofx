"""name-that-hash — hash identification tool."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry

@TaskRegistry.register("name-that-hash")
class NameThatHashTask(Task):
    name = "name-that-hash"
    cmd = "nth"
    description = "Hash identification tool"
    category = "crypto/identify"
    install_cmd = "uv tool install name-that-hash"
    output_types = [Tag]

    opts = {
        "greppable": OptDef(flag="-g", is_flag=True, help="Greppable output"),
        "json_output": OptDef(flag="-j", is_flag=True, help="JSON output"),
    }

    input_flag = "-t"
    file_flag = "-f"
    output_flag = None
    extra_flags = ["--no-banner"]

    def _output_suffix(self) -> str:
        return ".txt"

    _GREP_RE = re.compile(r"^(.+?):::(.+?):::")
    _TYPE_RE = re.compile(r"^\s+(\S.*?)\s+(?:HC:|JtR:)", re.IGNORECASE)

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
            line_stripped = line.rstrip()
            if not line_stripped:
                continue

            m_grep = self._GREP_RE.match(line_stripped)
            if m_grep:
                hash_val = m_grep.group(1).strip()
                types_str = m_grep.group(2).strip()
                type_name = types_str.split(" - ")[0].replace("Most Likely", "").strip()
                if not type_name:
                    type_name = types_str.split(" - ")[0].strip()
                if type_name:
                    results.append(
                        Tag(
                            name="hash_type",
                            value=type_name,
                            match=hash_val,
                            category="crypto",
                        )
                    )
                continue

            if not line_stripped.startswith(" ") and ":" not in line_stripped[:8]:
                current_hash = line_stripped.strip()
                continue

            m_type = self._TYPE_RE.match(line_stripped)
            if m_type:
                results.append(
                    Tag(
                        name="hash_type",
                        value=m_type.group(1).strip(),
                        match=current_hash,
                        category="crypto",
                    )
                )

        return results
