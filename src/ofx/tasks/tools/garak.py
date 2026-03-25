"""garak — LLM vulnerability scanner."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_FAIL_RE = re.compile(
    r"(?P<probe>\S+)\s+on\s+(?P<detector>\S+):\s+FAIL",
    re.IGNORECASE,
)
_PASS_RE = re.compile(
    r"(?P<probe>\S+)\s+on\s+(?P<detector>\S+):\s+PASS",
    re.IGNORECASE,
)


@TaskRegistry.register("garak")
class GarakTask(Task):
    name = "garak"
    cmd = "garak"
    description = "LLM vulnerability scanner"
    category = "vuln/llm"
    install_cmd = "uv tool install garak"
    output_types = [Vulnerability, Tag]

    opts = {
        "model_type": OptDef(flag="--model_type", type=str, help="Model type (e.g. huggingface, openai)"),
        "model_name": OptDef(flag="--model_name", type=str, help="Model name or endpoint"),
        "probes": OptDef(flag="--probes", type=str, help="Comma-separated probe modules"),
        "detectors": OptDef(flag="--detectors", type=str, help="Comma-separated detector modules"),
        "generations": OptDef(flag="--generations", type=int, help="Number of generations per probe"),
        "seed": OptDef(flag="--seed", type=int, help="Random seed"),
        "parallel_requests": OptDef(
            flag="--parallel_requests", type=int, help="Parallel request count"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["--report_prefix", "/tmp/.ofx_garak"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """All config goes through flags; *target* is treated as ``--model_name``."""
        parts: list[str] = [self.cmd, *self.extra_flags]

        if target and "model_name" not in kwargs:
            parts.extend(["--model_name", target])

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

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Try JSONL report lines first
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    pass
                else:
                    status = data.get("status", data.get("result", ""))
                    probe = data.get("probe", data.get("probe_name", ""))
                    detector = data.get("detector", "")
                    if str(status).upper() == "FAIL" and probe:
                        results.append(
                            Vulnerability(
                                name=f"LLM Probe Failure: {probe}",
                                matched_at=detector,
                                severity=Severity.HIGH,
                                provider="garak",
                                description=f"Probe {probe} failed on detector {detector}",
                                extra_data={k: v for k, v in data.items() if k not in ("status", "result")},
                            )
                        )
                    if probe:
                        results.append(Tag(name=probe, value=str(status), category="llm_probe"))
                    continue

            # Fall back to text summary parsing
            m_fail = _FAIL_RE.search(line)
            if m_fail:
                results.append(
                    Vulnerability(
                        name=f"LLM Probe Failure: {m_fail.group('probe')}",
                        matched_at=m_fail.group("detector"),
                        severity=Severity.HIGH,
                        provider="garak",
                        description=f"Probe {m_fail.group('probe')} failed on detector {m_fail.group('detector')}",
                    )
                )
                results.append(
                    Tag(name=m_fail.group("probe"), value="FAIL", category="llm_probe")
                )
                continue

            m_pass = _PASS_RE.search(line)
            if m_pass:
                results.append(
                    Tag(name=m_pass.group("probe"), value="PASS", category="llm_probe")
                )

        return results
