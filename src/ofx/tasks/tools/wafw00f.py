"""wafw00f — web application firewall detection tool."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Tag
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("wafw00f")
class Wafw00fTask(Task):
    name = "wafw00f"
    cmd = "wafw00f"
    description = "Web Application Firewall detection tool"
    category = "waf/detect"
    install_cmd = "uv tool install wafw00f"
    output_types = [Tag]

    opts = {
        "all": OptDef(flag="-a", is_flag=True, help="Test all WAF detections"),
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose output"),
        "proxy": OptDef(flag="-p", type=str, help="Use HTTP proxy"),
        "headers": OptDef(flag="-H", type=str, help="Custom header"),
        "test": OptDef(flag="-t", type=str, help="Test specific WAF"),
    }

    input_flag = None  # positional
    file_flag = "-i"
    output_flag = None
    extra_flags = []

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Tag]:
        results: list[Tag] = []
        lines = stdout.strip().splitlines() if stdout else []

        for line in lines:
            line = line.strip()
            # wafw00f outputs lines like:
            # [*] The site https://example.com is behind Cloudflare (Cloudflare Inc.)
            # [*] No WAF detected by the generic detection
            if "is behind" in line:
                # Extract WAF name and URL
                try:
                    parts = line.split("is behind", 1)
                    url_part = parts[0].strip()
                    waf_name = parts[1].strip().rstrip(".")

                    url = ""
                    for word in url_part.split():
                        if word.startswith("http://") or word.startswith("https://"):
                            url = word
                            break

                    if not waf_name:
                        continue

                    results.append(
                        Tag(
                            name=waf_name,
                            value=waf_name,
                            match=url,
                            category="waf",
                        )
                    )
                except (IndexError, ValueError):
                    continue

        return results
