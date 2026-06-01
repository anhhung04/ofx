"""Handler for ``ofx flow tasks run`` — execute a single task from the CLI.

Builds a :class:`TaskExecution` model, wraps it in a :class:`TaskRunner`,
and runs it directly without needing a YAML workflow file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import ofx.profiles.manager as profile_manager_module
from ofx.runner import RunContext, RunnerRegistryKeys
from ofx.runner.tasks.runner import TaskExecution, TaskRunner
import ofx.settings as settings_module
from ofx.settings import settings
from ofx.tasks import TaskRegistry

logger = logging.getLogger(settings.app_branding)


def _print_stdout_output(console, stdout: str) -> None:
    lines = stdout.strip().splitlines()
    display = lines[:50]
    for line in display:
        console.print(f"  {line}")
    if len(lines) > 50:
        console.print(f"  [dim]... {len(lines) - 50} more lines[/dim]")


class TaskRunHandler:
    """Execute a single registered task with CLI-provided options."""

    def __init__(
        self,
        task_name: str,
        target: str,
        opts: dict[str, Any],
        *,
        profile: str = "",
        timeout: int = 60,
        output: str = "",
        store_creds: bool = False,
        json_output: bool = False,
    ) -> None:
        self.task_name = task_name
        self.target = target
        self.opts = opts
        self.profile_name = profile
        self.timeout = timeout
        self.output = output
        self.store_creds = store_creds
        self.json_output = json_output

    async def run(self) -> int:
        console = settings_module.get_console()

        task_cls = TaskRegistry.get(self.task_name)
        if task_cls is None:
            available = TaskRegistry.list_tasks()
            console.print(f"[red]Task '{self.task_name}' is not registered.[/red]")
            if available:
                console.print(f"[dim]Available: {', '.join(available)}[/dim]")
            return 1

        profile = profile_manager_module.get_profile_manager().resolve_or_default(
            self.profile_name or None
        )

        output_path: Path | None = None
        if self.output:
            output_path = Path(self.output)
            output_path.mkdir(parents=True, exist_ok=True)

        ctx_vars: dict[str, Any] = {}
        if profile:
            ctx_vars["profile_model"] = profile
            ctx_vars["profile"] = profile.model_dump()
        ctx = RunContext(output_path=output_path, vars=ctx_vars)

        model = TaskExecution(
            task_name=self.task_name,
            target=self.target,
            opts=self.opts,
            timeout_minutes=self.timeout,
            store_creds=self.store_creds,
        )

        runner = TaskRunner(model, ctx)
        if not self.json_output:
            console.print(
                f"[bold cyan]Running task:[/bold cyan] {self.task_name} "
                f"[dim]target={self.target}[/dim]"
            )

        result = await runner.run()

        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
        typed_outputs = outputs.get("typed_outputs", [])
        stdout = outputs.get("stdout", "")
        exit_code = outputs.get("exit_code", None)

        if result.status.value == "failed":
            if self.json_output:
                print(
                    json.dumps(
                        {
                            "status": "failed",
                            "error": result.error,
                            "exit_code": exit_code,
                        }
                    )
                )
            else:
                console.print(f"[red]✗ Task failed:[/red] {result.error}")
            return 1

        if self.json_output:
            print(
                json.dumps(
                    {
                        "status": "success",
                        "exit_code": exit_code,
                        "typed_outputs": typed_outputs,
                        "stdout": stdout,
                    },
                    default=str,
                )
            )
        else:
            from rich.table import Table

            if typed_outputs:
                by_type: dict[str, list[dict]] = {}
                for item in typed_outputs:
                    type_name = item.get("_type", "unknown")
                    by_type.setdefault(type_name, []).append(item)

                for type_name, items in sorted(by_type.items()):
                    table = Table(
                        title=f"{type_name} ({len(items)})",
                        show_header=True,
                        header_style="bold cyan",
                        show_lines=False,
                    )

                    type_columns: dict[str, list[str]] = {
                        "port": ["ip", "port", "protocol", "service_name", "host"],
                        "ip": ["ip", "host", "alive"],
                        "subdomain": ["host", "domain"],
                        "url": ["url", "status_code", "title", "content_type"],
                        "vulnerability": ["severity", "name", "matched_at", "id"],
                        "tag": ["name", "value", "category", "match"],
                        "record": ["name", "type", "host"],
                        "domain": ["domain", "registrar", "alive"],
                        "certificate": ["host", "subject_cn", "issuer_cn", "not_after"],
                        "user_account": ["username", "password", "domain", "source"],
                        "exploit": ["id", "title"],
                    }

                    preferred = type_columns.get(type_name)
                    if preferred:
                        columns = [
                            column
                            for column in preferred
                            if any(item.get(column) for item in items[:10])
                        ]
                    elif items:
                        columns = [
                            key
                            for key in items[0]
                            if not key.startswith("_") and key != "extra_data"
                        ][:6]
                    else:
                        columns = []

                    for column in columns:
                        table.add_column(column, overflow="fold")

                    for item in items[:100]:
                        row = [str(item.get(column, "")) for column in columns]
                        table.add_row(*row)

                    if len(items) > 100:
                        table.caption = f"... and {len(items) - 100} more"

                    console.print(table)
                    console.print()

                console.print(
                    f"[green]✓[/green] {len(typed_outputs)} results "
                    f"({', '.join(f'{len(v)} {k}' for k, v in sorted(by_type.items()))})"
                )
            elif stdout:
                _print_stdout_output(console, stdout)
            else:
                console.print("[yellow]No output produced.[/yellow]")

        return 0


def parse_opt_args(opt_strings: list[str]) -> dict[str, Any]:
    """Parse ``--opt key=value`` strings into a dict.

    Supports:
      - ``key=value`` → str/int/float/bool coercion
      - ``key`` (no =) → True (boolean flag)
      - ``key=true/false`` → bool
    """
    def _parse_opt_value(val: str) -> Any:
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False
        try:
            return int(val)
        except ValueError:
            try:
                return float(val)
            except ValueError:
                return val

    result: dict[str, Any] = {}
    for opt in opt_strings:
        if "=" in opt:
            key, val = opt.split("=", 1)
            key = key.strip()
            val = val.strip()
            result[key] = _parse_opt_value(val)
        else:
            result[opt.strip()] = True
    return result
