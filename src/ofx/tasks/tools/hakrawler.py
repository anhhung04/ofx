"""hakrawler — fast web crawler for discovering URLs and endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("hakrawler")
class HakrawlerTask(Task):
    name = "hakrawler"
    cmd = "hakrawler"
    description = "Fast web crawler for discovering URLs and endpoints"
    category = "url/crawl"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/hakluke/hakrawler@latest"
    output_types = [Url]

    opts = {
        "depth": OptDef(flag="-d", type=int, help="Crawl depth (default 2)"),
        "insecure": OptDef(
            flag="-insecure", is_flag=True, help="Skip TLS verification"
        ),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "timeout": OptDef(flag="-timeout", type=int, help="Timeout per URL in seconds"),
        "proxy": OptDef(flag="-proxy", type=str, help="Proxy URL"),
        "subs": OptDef(flag="-subs", is_flag=True, help="Include subdomains"),
        "json": OptDef(flag="-json", is_flag=True, help="JSON output"),
        "inside": OptDef(flag="-i", is_flag=True, help="Only crawl inside path"),
        "unique": OptDef(flag="-u", is_flag=True, help="Show only unique URLs"),
        "size": OptDef(flag="-size", type=int, help="Page size limit in KB"),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    silent_flag = "-s"

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``echo "{target}" | hakrawler [options]``."""
        parts: list[str] = [self.cmd]

        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        parts.extend(self._build_opt_parts(kwargs))

        cmd_str = f"echo {self._q(target)} | {' '.join(parts)}"
        return cmd_str, None

    def parse_line(self, line: str) -> list[Url]:
        line = line.strip()
        if not line or line.startswith("["):
            return []
        if "://" in line:
            return [Url(url=line)]
        return []
