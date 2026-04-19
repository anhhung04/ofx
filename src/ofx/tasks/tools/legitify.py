"""legitify — GitHub/GitLab security posture scanner."""

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
}


@TaskRegistry.register("legitify")
class LegitifyTask(Task):
    name = "legitify"
    cmd = "legitify"
    description = "GitHub/GitLab security posture scanner"
    category = "recon/cicd"
    install_cmd = (
        "GOBIN=~/Tools/bin go install -v"
        " github.com/Legit-Labs/legitify@latest"
    )
    output_types = [Vulnerability, Tag]

    opts = {
        "org": OptDef(flag="--org", type=str, help="Target organization"),
        "repo": OptDef(flag="--repo", type=str, help="Target repository"),
        "token": OptDef(flag="--token", type=str, help="SCM access token"),
        "output_format": OptDef(flag="-o", type=str, help="Output format"),
        "severity_filter": OptDef(flag="--severity", type=str, help="Severity filter"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["-o", "json"]

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Target is the org name, passed via ``--org``."""
        parts: list[str] = [self.cmd, *self.extra_flags]

        # If target provided and --org not already in kwargs
        if target and "org" not in kwargs and "repo" not in kwargs:
            parts.extend(["--org", target])

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
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        results: list[Vulnerability | Tag] = []

        # Legitify JSON may be a list or dict with nested violation arrays
        violations: list[dict[str, Any]] = []
        if isinstance(data, list):
            violations = data
        elif isinstance(data, dict):
            for section in data.values():
                if isinstance(section, list):
                    violations.extend(section)
                elif isinstance(section, dict):
                    for items in section.values():
                        if isinstance(items, list):
                            violations.extend(items)

        for v in violations:
            if not isinstance(v, dict):
                continue
            policy = v.get("policy_name", v.get("policy", v.get("title", "")))
            sev = str(v.get("severity", "medium")).lower()
            entity = v.get("entity", v.get("entity_name", v.get("resource", "")))
            desc = v.get("description", v.get("aux", {}).get("description", ""))

            results.append(
                Vulnerability(
                    name=str(policy),
                    matched_at=str(entity),
                    severity=_SEVERITY_MAP.get(sev, Severity.MEDIUM),
                    provider="legitify",
                    description=str(desc),
                    extra_data={k: v for k, v in v.items() if k not in ("policy_name", "severity", "entity", "description")},
                )
            )
            results.append(Tag(name=str(policy), value=sev, category="scm_posture"))

        return results
