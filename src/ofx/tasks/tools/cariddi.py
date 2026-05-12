"""cariddi — crawl URLs for secrets, endpoints, and errors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag, Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("cariddi")
class CariddiTask(Task):
    name = "cariddi"
    cmd = "cariddi"
    description = "Crawl URLs for secrets, endpoints, and errors"
    category = "url/crawl"
    install_cmd = (
        "GOBIN=$TOOLS_BIN_DIR go install -v"
        " github.com/edoardottt/cariddi/cmd/cariddi@latest"
    )
    output_types = [Url, Tag]

    opts = {
        "threads": OptDef(flag="-c", type=int, help="Concurrency level"),
        "timeout": OptDef(flag="-t", type=int, help="Timeout in seconds"),
        "delay": OptDef(flag="-d", type=int, help="Delay between requests in ms"),
        "depth": OptDef(flag="-depth", type=int, help="Crawl depth"),
        "headers": OptDef(flag="-headers", type=str, help="Custom headers"),
        "proxy": OptDef(flag="-proxy", type=str, help="Proxy URL"),
        "secrets": OptDef(
            flag="-s", is_flag=True, help="Hunt for secrets (already in extra_flags)"
        ),
        "errors": OptDef(flag="-err", is_flag=True, help="Hunt for errors"),
        "info": OptDef(
            flag="-info",
            is_flag=True,
            help="Hunt for info disclosures (already in extra_flags)",
        ),
    }

    input_flag = None  # reads from stdin
    file_flag = None
    output_flag = None  # stdout JSON
    json_flag = "-json"
    silent_flag = "-s"
    extra_flags = ["-e", "-info"]

    def _output_suffix(self) -> str:
        return ".jsonl"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Pipe target into cariddi via stdin."""
        parts: list[str] = [*self.extra_flags]
        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        for key, value in kwargs.items():
            if key.startswith("_"):
                continue
            opt = self.opts.get(key)
            if opt is None:
                continue
            # Skip flags already present in extra_flags
            if opt.flag in self.extra_flags:
                continue
            if opt.is_flag:
                if value:
                    parts.append(opt.flag)
            elif value is not None:
                parts.extend([opt.flag, self._q(value)])

        cmd = f'echo {self._q(target)} | {self.cmd} {" ".join(parts)}'

        return cmd, None

    def parse_line(self, line: str) -> list[Url | Tag]:
        data = self._parse_json_line(line)
        if data is None:
            return []

        results: list[Url | Tag] = []

        url = data.get("url", "")
        if url:
            results.append(
                Url(
                    url=url,
                    status_code=self._safe_int(data.get("status_code", 0)),
                )
            )

        for match in data.get("matches", []):
            name = match.get("name", match.get("type", ""))
            value = match.get("match", "")
            category = match.get("type", "secret")
            if name or value:
                results.append(
                    Tag(
                        name=name,
                        value=value,
                        match=url,
                        category=category,
                    )
                )

        # Handle top-level secrets/errors/infos arrays
        for section, cat in (
            ("secrets", "secret"),
            ("errors", "error"),
            ("infos", "info"),
        ):
            for item in data.get(section, []):
                if isinstance(item, str):
                    results.append(Tag(name=cat, value=item, match=url, category=cat))
                elif isinstance(item, dict):
                    results.append(
                        Tag(
                            name=item.get("name", cat),
                            value=item.get("match", str(item)),
                            match=url,
                            category=cat,
                        )
                    )

        return results
