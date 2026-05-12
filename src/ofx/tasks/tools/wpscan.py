"""wpscan — WordPress security scanner."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Tag, Vulnerability
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("wpscan")
class WpscanTask(Task):
    name = "wpscan"
    cmd = "wpscan"
    description = "WordPress security scanner"
    category = "vuln/scan/wordpress"
    install_cmd = "GEM_HOME=$TOOLS_DIR gem install wpscan"
    output_types = [Vulnerability, Tag]

    # wpscan: exit 5 = vulnerabilities found — that's expected useful output.
    success_codes = [0, 5]

    opts = {
        "enumerate": OptDef(
            flag="-e",
            type=str,
            help="Enumerate: vp,vt,u,m,ap,at,cb,dbe",
        ),
        "api_token": OptDef(flag="--api-token", type=str, help="WPScan API token"),
        "stealthy": OptDef(flag="--stealthy", is_flag=True, help="Use stealthy mode"),
        "random_user_agent": OptDef(
            flag="--random-user-agent",
            is_flag=True,
            help="Use a random user agent",
        ),
        "wp_content_dir": OptDef(
            flag="--wp-content-dir",
            type=str,
            help="Custom wp-content directory",
        ),
        "detection_mode": OptDef(
            flag="--detection-mode",
            type=str,
            help="Detection mode: mixed/passive/aggressive",
        ),
    }

    input_flag = "--url"
    file_flag = None
    output_flag = None
    extra_flags = ["--format", "json", "--force", "--no-banner"]

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
        target_url = data.get("target_url", "")

        # Parse plugins, themes, and main_theme sections
        for section in ("plugins", "themes", "main_theme"):
            items = data.get(section, {})
            if isinstance(items, dict):
                for key, item in items.items():
                    if not isinstance(item, dict):
                        continue
                    self._parse_component(results, key, item, target_url, section)

        return results

    @staticmethod
    def _parse_component(
        results: list[Vulnerability | Tag],
        key: str,
        item: dict,
        url: str,
        section: str,
    ) -> None:
        """Extract vulnerabilities and tags from a plugin/theme component."""
        if not key:
            return

        # Detected component tag
        version_info = item.get("version", {})
        version_number = ""
        if isinstance(version_info, dict):
            version_number = version_info.get("number", "")

        if version_number:
            results.append(
                Tag(
                    name=key,
                    value=version_number,
                    match=url,
                    category="wordpress",
                )
            )

        # Vulnerabilities in this component
        for vuln in item.get("vulnerabilities", []):
            title = vuln.get("title", "")
            if not title:
                continue
            refs = vuln.get("references", {})
            cve_list = refs.get("cve", [])
            cve_id = cve_list[0] if cve_list else ""
            wpvulndb = refs.get("wpvulndb", [])

            results.append(
                Vulnerability(
                    name=title,
                    id=cve_id,
                    severity=Severity.MEDIUM,
                    matched_at=url,
                    provider="wpscan",
                    tags=wpvulndb,
                )
            )
