"""schemathesis — OpenAPI / GraphQL property-based API testing."""

from __future__ import annotations

import re
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Severity, Url, Vulnerability
from ofx.tasks.registry import TaskRegistry

# Match failure/error lines like:
#   FAILED: GET /api/users 500 server_error
#   Failure: POST /items [not_a_server_error] ...
_FAILURE_RE = re.compile(
    r"(?:FAIL(?:ED|URE)?|ERROR)\s*:?\s*"
    r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)?\s*"
    r"(/\S*)\s*"
    r"(\d{3})?\s*"
    r"([\w_.-]+)?",
    re.IGNORECASE,
)


@TaskRegistry.register("schemathesis")
class SchemathesisTask(Task):
    name = "schemathesis"
    cmd = "schemathesis"
    description = "OpenAPI / GraphQL property-based API testing"
    category = "vuln/api"
    install_cmd = "uv tool install schemathesis"
    output_types = [Vulnerability, Url]

    opts = {
        "base_url": OptDef(flag="--base-url", type=str, help="Base URL of the API"),
        "workers": OptDef(flag="-w", type=int, help="Number of concurrent workers"),
        "checks": OptDef(
            flag="-c", type=str, help="Checks to run (e.g. all, not_a_server_error)"
        ),
        "stateful": OptDef(
            flag="--stateful", type=str, help="Stateful testing mode (links)"
        ),
        "hypothesis_max_examples": OptDef(
            flag="--hypothesis-max-examples",
            type=int,
            help="Max test examples per endpoint",
        ),
        "method": OptDef(flag="-M", type=str, help="Filter by HTTP method"),
        "endpoint": OptDef(flag="-E", type=str, help="Filter by endpoint regex"),
        "auth": OptDef(flag="-a", type=str, help="Auth credentials (user:pass)"),
        "header": OptDef(flag="-H", type=str, help="Custom header"),
        "validate_schema": OptDef(
            flag="--validate-schema",
            is_flag=True,
            help="Validate API schema conformance",
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    extra_flags = ["run", "--dry-run=never"]

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Vulnerability | Url]:
        raw = self._raw_output(stdout, output_file)
        if not raw:
            return []

        results: list[Vulnerability | Url] = []
        seen_paths: set[str] = set()

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            m = _FAILURE_RE.search(line)
            if not m:
                continue

            method = m.group(1) or ""
            path = m.group(2) or ""
            status = m.group(3) or ""
            check = m.group(4) or ""

            desc_parts: list[str] = []
            if method:
                desc_parts.append(method)
            if status:
                desc_parts.append(f"status={status}")
            if check:
                desc_parts.append(f"check={check}")

            results.append(
                Vulnerability(
                    name="API Schema Violation",
                    matched_at=path,
                    severity=Severity.MEDIUM,
                    provider="schemathesis",
                    description=" ".join(desc_parts) if desc_parts else line,
                    extra_data={"method": method, "status": status, "check": check},
                )
            )

            if path and path not in seen_paths:
                seen_paths.add(path)
                results.append(Url(url=path, method=method))

        return results
