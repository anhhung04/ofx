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
        "insecure": OptDef(flag="-insecure", is_flag=True, help="Skip TLS verification"),
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
    extra_flags: list[str] = ["-s"]

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Build: ``echo "{target}" | hakrawler [options]``."""
        parts: list[str] = [self.cmd]

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

        cmd_str = f"echo {target!r} | {' '.join(parts)}"
        return cmd_str, None

    def parse_line(self, line: str) -> list[Url]:
        line = line.strip()
        if not line or line.startswith("["):
            return []
        if "://" in line:
            return [Url(url=line)]
        return []

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url]:
        results: list[Url] = []
        lines: list[str] = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))

        return results
