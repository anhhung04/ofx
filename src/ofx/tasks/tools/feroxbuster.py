"""feroxbuster — fast content discovery tool written in Rust."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("feroxbuster")
class FeroxbusterTask(Task):
    name = "feroxbuster"
    cmd = "feroxbuster"
    description = "Fast content discovery tool written in Rust"
    category = "url/fuzz"
    install_cmd = "mkdir -p ~/Tools/bin && cd ~/Tools/bin && curl -sL https://raw.githubusercontent.com/epi052/feroxbuster/main/install-nix.sh | bash"
    output_types = [Url]

    opts = {
        "wordlist": OptDef(flag="-w", type=str, help="Wordlist path"),
        "threads": OptDef(flag="-t", type=int, help="Number of concurrent threads"),
        "depth": OptDef(flag="-d", type=int, help="Maximum recursion depth"),
        "timeout": OptDef(flag="-T", type=int, help="Request timeout in seconds"),
        "status_codes": OptDef(
            flag="-s", type=str, help="Status codes to include (e.g. 200,301,302)"
        ),
        "filter_status": OptDef(flag="-C", type=str, help="Status codes to exclude"),
        "filter_size": OptDef(flag="-S", type=str, help="Response sizes to exclude"),
        "filter_words": OptDef(flag="-W", type=str, help="Word counts to exclude"),
        "filter_lines": OptDef(flag="-N", type=str, help="Line counts to exclude"),
        "filter_regex": OptDef(
            flag="--filter-regex", type=str, help="Regex to filter responses"
        ),
        "extensions": OptDef(
            flag="-x", type=str, help="File extensions to search (e.g. php,html,js)"
        ),
        "methods": OptDef(flag="-m", type=str, help="HTTP methods (e.g. GET,POST)"),
        "headers": OptDef(flag="-H", type=str, help="HTTP header(s)"),
        "data": OptDef(flag="--data", type=str, help="POST body data"),
        "proxy": OptDef(flag="-p", type=str, help="Proxy URL"),
        "rate_limit": OptDef(
            flag="--rate-limit", type=int, help="Max requests per second"
        ),
        "insecure": OptDef(flag="-k", is_flag=True, help="Disable TLS verification"),
        "no_recursion": OptDef(flag="-n", is_flag=True, help="Do not recurse"),
        "redirects": OptDef(flag="-r", is_flag=True, help="Follow redirects"),
        "extract_links": OptDef(
            flag="-e", is_flag=True, help="Extract links from response body"
        ),
        "auto_tune": OptDef(
            flag="--auto-tune", is_flag=True, help="Automatically adjust scan speed"
        ),
        "dont_filter": OptDef(
            flag="--dont-filter", is_flag=True, help="Don't auto-filter responses"
        ),
        "collect_words": OptDef(
            flag="--collect-words", is_flag=True, help="Collect discovered words"
        ),
        "smart": OptDef(
            flag="--smart", is_flag=True, help="Smart mode: auto-detect extensions and filter 404s"
        ),
        "collect_extensions": OptDef(
            flag="--collect-extensions",
            is_flag=True,
            help="Collect discovered extensions for targeted scanning",
        ),
        "force_recursion": OptDef(
            flag="--force-recursion",
            is_flag=True,
            help="Force recursion on all found directories",
        ),
        "user_agent": OptDef(
            flag="-a", type=str, help="Custom User-Agent string"
        ),
    }

    input_flag = "-u"
    file_flag = "--stdin"
    output_flag = "-o"
    extra_flags = ["--json", "--silent", "--no-state"]

    def build_command(
        self, target: str, **kwargs: Any
    ) -> tuple[str, Path | None]:
        """Override to pipe file/multi-line targets via stdin.

        feroxbuster's ``--stdin`` reads URLs from stdin (one per line),
        unlike most tools where the file flag takes a path argument.
        """
        target_is_file = (
            target
            and not target.startswith("http")
            and Path(target).is_file()
        )
        has_newlines = target and "\n" in target

        if target_is_file or has_newlines:
            # Write multi-line string to a temp file if needed
            if has_newlines and not target_is_file:
                tmp = tempfile.NamedTemporaryFile(
                    mode="w",
                    prefix=".ofx_ferox_targets_",
                    suffix=".txt",
                    delete=False,
                )
                tmp.write(target)
                tmp.close()
                file_path = tmp.name
            else:
                file_path = target

            # Build command WITHOUT target, then prepend cat pipe
            saved = self.file_flag
            self.file_flag = None
            cmd, output_file = super().build_command("", **kwargs)
            self.file_flag = saved
            cmd = f"cat {file_path} | {cmd} --stdin"
            return cmd, output_file

        return super().build_command(target, **kwargs)

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_line(self, line: str) -> list[Url]:
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        # feroxbuster JSON has type field; we only want "response" entries
        entry_type = data.get("type", "")
        if entry_type and entry_type != "response":
            return []

        url = data.get("url", "")
        if not url:
            return []

        return [
            Url(
                url=url,
                host="",
                status_code=self._safe_int(data.get("status", 0)),
                content_length=self._safe_int(data.get("content_length", 0)),
                words=self._safe_int(data.get("word_count", 0)),
                lines=self._safe_int(data.get("line_count", 0)),
                method=data.get("method", "GET"),
            )
        ]

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
