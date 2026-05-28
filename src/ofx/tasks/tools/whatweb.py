"""whatweb — web fingerprinting and technology identification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("whatweb")
class WhatwebTask(Task):
    name = "whatweb"
    cmd = "whatweb"
    description = "Web fingerprinting and technology identification"
    category = "url/fingerprint"
    install_cmd = "apt install -y whatweb"
    output_types = [Tag]

    opts = {
        "aggression": OptDef(
            flag="-a",
            type=int,
            help="1=stealthy, 3=aggressive, 4=heavy",
        ),
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "user_agent": OptDef(flag="-U", type=str, help="Custom User-Agent"),
        "proxy": OptDef(flag="--proxy", type=str, help="HTTP proxy"),
        "follow_redirect": OptDef(
            flag="--follow-redirect",
            type=str,
            help="always/never/same-site",
        ),
    }

    input_flag = None  # positional
    file_flag = "-i"
    output_flag = "--log-json"
    silent_flag = "-q"
    extra_flags = ["--color=never"]

    def _output_suffix(self) -> str:
        return ".json"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Override to place positional target after flags and output file."""
        parts: list[str] = [self.cmd, *self.extra_flags]
        if self.json_flag:
            parts.append(self.json_flag)
        if self.silent_flag:
            parts.append(self.silent_flag)

        parts.extend(self._build_opt_parts(kwargs))

        output_file: Path | None = None
        if self.output_flag:
            output_file = self._make_output_path()
            parts.extend([self.output_flag, str(output_file)])

        parts.append(self._q(target))

        return " ".join(parts), output_file

    def _parse_json_entry(self, entry: dict) -> list[Tag]:
        """Extract Tag results from a single whatweb JSON entry."""
        if not isinstance(entry, dict):
            return []

        target_url = entry.get("target", "")
        plugins = entry.get("plugins", {})

        if not isinstance(plugins, dict):
            return []

        results: list[Tag] = []
        for plugin_name, plugin_data in plugins.items():
            version = ""
            string_val = ""
            if isinstance(plugin_data, dict):
                versions = plugin_data.get("version", [])
                if isinstance(versions, list) and versions:
                    version = str(versions[0])
                elif isinstance(versions, str):
                    version = versions

                strings = plugin_data.get("string", [])
                if isinstance(strings, list) and strings:
                    string_val = ", ".join(str(s) for s in strings)
                elif isinstance(strings, str):
                    string_val = strings

            value = version or string_val
            if not value:
                continue

            results.append(
                Tag(
                    name=plugin_name,
                    value=value,
                    match=target_url,
                    category="tech",
                )
            )

        return results

    def parse_line(self, line: str) -> list[Tag]:
        line = line.strip()
        if not line:
            return []
        entry = self._parse_json_line(line)
        if entry is None:
            return []
        return self._parse_json_entry(entry)

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[Tag] = []
        for line in raw.splitlines():
            results.extend(self.parse_line(line))

        return results
