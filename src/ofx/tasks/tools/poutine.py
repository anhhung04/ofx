"""poutine — CI/CD pipeline security scanner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_SEVERITY_MAP = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
    "note": Severity.INFO,
    "warning": Severity.MEDIUM,
    "error": Severity.HIGH,
}


@TaskRegistry.register("poutine")
class PoutineTask(Task):
    name = "poutine"
    cmd = "poutine"
    description = "CI/CD pipeline security scanner"
    category = "vuln/cicd"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v"
        " github.com/boostsecurityio/poutine@latest"
    )
    output_types = [Vulnerability, Tag]

    opts = {
        "format": OptDef(flag="-f", type=str, help="Output format (json, sarif, pretty)"),
        "token": OptDef(flag="--token", type=str, help="GitHub/GitLab token"),
        "threads": OptDef(flag="--threads", type=int, help="Number of threads"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["analyze_repo", "-f", "json"]

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """``poutine analyze_repo -f json <org/repo>``."""
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

        if target:
            parts.append(target)

        return " ".join(parts), None

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Tag]:
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        findings = data if isinstance(data, list) else data.get("findings", data.get("results", []))
        if not isinstance(findings, list):
            return []

        results: list[Vulnerability | Tag] = []
        for finding in findings:
            rule = finding.get("rule", finding.get("rule_id", finding.get("id", "")))
            sev = str(finding.get("severity", finding.get("level", "medium"))).lower()
            file_path = finding.get("file", finding.get("path", finding.get("location", "")))
            line_num = finding.get("line", finding.get("line_number", ""))
            desc = finding.get("description", finding.get("message", ""))
            matched = f"{file_path}:{line_num}" if line_num else str(file_path)

            results.append(
                Vulnerability(
                    name=str(rule),
                    matched_at=matched,
                    severity=_SEVERITY_MAP.get(sev, Severity.MEDIUM),
                    provider="poutine",
                    description=str(desc),
                    extra_data={k: v for k, v in finding.items() if k not in ("rule", "severity", "file", "description")},
                )
            )
            results.append(Tag(name=str(rule), value=sev, category="cicd"))

        return results
