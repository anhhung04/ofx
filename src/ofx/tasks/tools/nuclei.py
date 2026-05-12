"""nuclei — fast template-based vulnerability scanner."""

from __future__ import annotations

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Confidence, Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry

_SEVERITY_MAP = {
    "info": Severity.INFO,
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
    "critical": Severity.CRITICAL,
}


@TaskRegistry.register("nuclei")
class NucleiTask(Task):
    name = "nuclei"
    cmd = "nuclei"
    description = "Fast and customisable vulnerability scanner based on YAML templates"
    category = "vuln/scan"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"
    output_types = [Vulnerability, Tag]

    opts = {
        "templates": OptDef(flag="-t", type=str, help="Template or directory path"),
        "tags": OptDef(flag="-tags", type=str, help="Run templates with matching tags"),
        "exclude_tags": OptDef(
            flag="-etags", type=str, help="Exclude templates with tags"
        ),
        "severity": OptDef(flag="-severity", type=str, help="Filter by severity"),
        "rate_limit": OptDef(
            flag="-rate-limit", type=int, help="Max requests per second"
        ),
        "bulk_size": OptDef(flag="-bulk-size", type=int, help="Max hosts per template"),
        "concurrency": OptDef(
            flag="-concurrency", type=int, help="Max templates in parallel"
        ),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout in seconds"),
        "retries": OptDef(flag="-retries", type=int, help="Number of retries"),
        "headless": OptDef(
            flag="-headless", is_flag=True, help="Enable headless browser"
        ),
        "new_templates": OptDef(
            flag="-new-templates", is_flag=True, help="Run new templates only"
        ),
        "automatic_scan": OptDef(
            flag="-automatic-scan", is_flag=True, help="Automatic web scan"
        ),
    }

    input_flag = "-u"
    file_flag = "-l"
    output_flag = "-o"
    json_flag = "-jsonl"
    silent_flag = "-silent"

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Vulnerability | Tag]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        info = data.get("info", {})
        template_id = data.get("template-id", data.get("template_id", ""))
        matched_at = data.get("matched-at", data.get("host", ""))
        severity_str = info.get("severity", "unknown").lower()

        tags_raw = info.get("tags", [])
        if isinstance(tags_raw, str):
            tags_raw = [t.strip() for t in tags_raw.split(",")]

        references = info.get("reference", [])
        if isinstance(references, str):
            references = [references]

        results: list[Vulnerability | Tag] = [
            Vulnerability(
                name=info.get("name", template_id),
                id=template_id,
                matched_at=matched_at,
                severity=_SEVERITY_MAP.get(severity_str, Severity.UNKNOWN),
                confidence=Confidence.HIGH,
                provider="nuclei",
                description=info.get("description", ""),
                tags=tags_raw,
                references=references,
                extra_data={
                    k: v
                    for k, v in data.items()
                    if k not in ("info", "template-id", "matched-at", "host")
                },
            )
        ]

        for tag in tags_raw:
            results.append(
                Tag(name=tag, value=tag, match=matched_at, category="nuclei")
            )

        return results
