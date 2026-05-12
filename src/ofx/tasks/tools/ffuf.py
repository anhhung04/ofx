"""ffuf — fast web fuzzer written in Go."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("ffuf")
class FfufTask(Task):
    name = "ffuf"
    cmd = "ffuf"
    description = "Fast web fuzzer written in Go"
    category = "url/fuzz"
    install_cmd = "GOBIN=$TOOLS_BIN_DIR go install github.com/ffuf/ffuf/v2@latest"
    output_types = [Url]

    opts = {
        "wordlist": OptDef(flag="-w", type=str, help="Wordlist path (e.g. /path:FUZZ)"),
        "method": OptDef(flag="-X", type=str, help="HTTP method"),
        "headers": OptDef(flag="-H", type=str, help="Header (repeatable)"),
        "data": OptDef(flag="-d", type=str, help="POST data"),
        "match_codes": OptDef(flag="-mc", type=str, help="Match HTTP status codes"),
        "filter_codes": OptDef(flag="-fc", type=str, help="Filter HTTP status codes"),
        "match_size": OptDef(flag="-ms", type=str, help="Match response size"),
        "filter_size": OptDef(flag="-fs", type=str, help="Filter response size"),
        "match_words": OptDef(flag="-mw", type=str, help="Match word count"),
        "filter_words": OptDef(flag="-fw", type=str, help="Filter word count"),
        "match_lines": OptDef(flag="-ml", type=str, help="Match line count"),
        "filter_lines": OptDef(flag="-fl", type=str, help="Filter line count"),
        "match_regex": OptDef(flag="-mr", type=str, help="Match regex pattern"),
        "filter_regex": OptDef(flag="-fr", type=str, help="Filter regex pattern"),
        "threads": OptDef(flag="-t", type=int, help="Number of concurrent threads"),
        "rate": OptDef(flag="-rate", type=int, help="Rate of requests per second"),
        "timeout": OptDef(flag="-timeout", type=int, help="HTTP request timeout"),
        "recursion": OptDef(flag="-recursion", is_flag=True, help="Enable recursion"),
        "recursion_depth": OptDef(
            flag="-recursion-depth", type=int, help="Max recursion depth"
        ),
        "follow_redirects": OptDef(flag="-r", is_flag=True, help="Follow redirects"),
        "extensions": OptDef(flag="-e", type=str, help="File extension list"),
        "auto_calibration": OptDef(
            flag="-ac", is_flag=True, help="Automatically calibrate filtering"
        ),
    }

    input_flag = "-u"
    file_flag = None
    output_flag = "-o"
    silent_flag = "-s"
    extra_flags = ["-noninteractive", "-of", "json"]

    def _output_suffix(self) -> str:
        return ".json"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Url]:
        results: list[Url] = []
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return results

        entries = data.get("results", [])
        if not isinstance(entries, list):
            return results

        for entry in entries:
            url = entry.get("url", "")
            if not url:
                continue

            host = entry.get("host", "")
            results.append(
                Url(
                    url=url,
                    host=host,
                    status_code=self._safe_int(entry.get("status", 0)),
                    content_length=self._safe_int(entry.get("length", 0)),
                    content_type=entry.get("content-type", ""),
                    words=self._safe_int(entry.get("words", 0)),
                    lines=self._safe_int(entry.get("lines", 0)),
                    method=entry.get(
                        "method", entry.get("input", {}).get("method", "")
                    ),
                )
            )

        return results
