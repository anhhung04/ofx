"""promptfoo — LLM red teaming and evaluation framework."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_RESULT_RE = re.compile(
    r"(?P<status>PASS|FAIL)\s+(?P<description>.+)",
    re.IGNORECASE,
)


@TaskRegistry.register("promptfoo")
class PromptfooTask(Task):
    name = "promptfoo"
    cmd = "promptfoo"
    description = "LLM red teaming and evaluation framework"
    category = "vuln/llm"
    install_cmd = "npm install -g promptfoo"
    output_types = [Vulnerability, Tag]

    opts = {
        "config": OptDef(flag="-c", type=str, help="Config file path"),
        "providers": OptDef(flag="--providers", type=str, help="Provider(s) to test"),
        "output_format": OptDef(flag="-o", type=str, help="Output format"),
        "max_concurrency": OptDef(flag="-j", type=int, help="Max concurrency"),
        "no_cache": OptDef(flag="--no-cache", is_flag=True, help="Disable cache"),
        "env_file": OptDef(flag="--env-file", type=str, help="Environment file"),
        "filter_failing": OptDef(
            flag="--filter-failing", is_flag=True, help="Show only failing tests"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["redteam", "run"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """``promptfoo redteam run`` with config or provider as target."""
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

        # If target looks like a file path use -c, otherwise --providers
        if target:
            if Path(target).suffix in {".yml", ".yaml", ".json"} or Path(target).is_file():
                if "config" not in kwargs:
                    parts.extend(["-c", target])
            elif "providers" not in kwargs:
                parts.extend(["--providers", target])

        return " ".join(parts), None

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Tag]:
        raw = ""
        if output_file and output_file.exists():
            raw = self._read_output_file(output_file)
        elif stdout:
            raw = stdout

        raw = raw.strip()
        if not raw:
            return []

        results: list[Vulnerability | Tag] = []
        fail_count = 0
        pass_count = 0

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            m = _RESULT_RE.search(line)
            if m:
                status = m.group("status").upper()
                desc = m.group("description").strip()
                if status == "FAIL":
                    fail_count += 1
                    results.append(
                        Vulnerability(
                            name="LLM Red Team Failure",
                            matched_at=desc,
                            severity=Severity.MEDIUM,
                            provider="promptfoo",
                            description=desc,
                        )
                    )
                else:
                    pass_count += 1

        if fail_count or pass_count:
            results.append(
                Tag(
                    name="promptfoo_summary",
                    value=f"pass={pass_count} fail={fail_count}",
                    category="llm_redteam",
                )
            )

        return results
