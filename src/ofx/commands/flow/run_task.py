"""Handler for ``ofx flow tasks run`` — execute a single task from the CLI.

Builds a :class:`TaskExecution` model, wraps it in a :class:`TaskRunner`,
and runs it directly without needing a YAML workflow file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ofx.runner.core import RunContext, RunnerRegistryKeys
from ofx.runner.tasks.runner import TaskExecution, TaskRunner
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


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
        from ofx.settings import get_console
        from ofx.tasks import TaskRegistry

        console = get_console()

        # Validate task exists
        task_cls = TaskRegistry.get(self.task_name)
        if task_cls is None:
            available = TaskRegistry.list_tasks()
            console.print(f"[red]Task '{self.task_name}' is not registered.[/red]")
            if available:
                console.print(f"[dim]Available: {', '.join(available)}[/dim]")
            return 1

        # Resolve profile
        profile = None
        if self.profile_name:
            from ofx.profiles.manager import get_profile_manager

            mgr = get_profile_manager()
            profile = mgr.resolve_or_default(self.profile_name)
        else:
            from ofx.profiles.manager import get_profile_manager

            mgr = get_profile_manager()
            profile = mgr.resolve_or_default(None)

        # Build output path
        output_path: Path | None = None
        if self.output:
            output_path = Path(self.output)
            output_path.mkdir(parents=True, exist_ok=True)

        # Build run context
        ctx_vars: dict[str, Any] = {}
        if profile:
            ctx_vars["profile_model"] = profile
            ctx_vars["profile"] = profile.model_dump()
        ctx = RunContext(output_path=output_path, vars=ctx_vars)

        # Build task execution model
        model = TaskExecution(
            task_name=self.task_name,
            target=self.target,
            opts=self.opts,
            timeout_minutes=self.timeout,
            store_creds=self.store_creds,
        )

        # Run
        runner = TaskRunner(model, ctx)
        if not self.json_output:
            console.print(
                f"[bold cyan]Running task:[/bold cyan] {self.task_name} "
                f"[dim]target={self.target}[/dim]"
            )

        result = await runner.run()

        # Retrieve outputs
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

        # Display results
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
            _display_results(console, typed_outputs, stdout)

        return 0


def _display_results(
    console: Any,
    typed_outputs: list[dict],
    stdout: str,
) -> None:
    """Display task results using Rich tables."""
    from rich.table import Table

    if typed_outputs:
        # Group by type
        by_type: dict[str, list[dict]] = {}
        for item in typed_outputs:
            t = item.get("_type", "unknown")
            by_type.setdefault(t, []).append(item)

        for type_name, items in sorted(by_type.items()):
            table = Table(
                title=f"{type_name} ({len(items)})",
                show_header=True,
                header_style="bold cyan",
                show_lines=False,
            )

            # Auto-detect columns from first few items
            columns = _pick_columns(type_name, items)
            for col in columns:
                table.add_column(col, overflow="fold")

            for item in items[:100]:  # cap display at 100
                row = [str(item.get(c, "")) for c in columns]
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
        lines = stdout.strip().splitlines()
        display = lines[:50]
        for line in display:
            console.print(f"  {line}")
        if len(lines) > 50:
            console.print(f"  [dim]... {len(lines) - 50} more lines[/dim]")
    else:
        console.print("[yellow]No output produced.[/yellow]")


def _pick_columns(type_name: str, items: list[dict]) -> list[str]:
    """Pick the most useful columns for display based on output type."""
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
        # Only include columns that have data
        return [c for c in preferred if any(item.get(c) for item in items[:10])]

    # Fallback: pick keys from first item, skip internal fields
    if items:
        return [
            k
            for k in items[0]
            if not k.startswith("_") and k != "extra_data"
        ][:6]
    return []


def parse_opt_args(opt_strings: list[str]) -> dict[str, Any]:
    """Parse ``--opt key=value`` strings into a dict.

    Supports:
      - ``key=value`` → str/int/float/bool coercion
      - ``key`` (no =) → True (boolean flag)
      - ``key=true/false`` → bool
    """
    result: dict[str, Any] = {}
    for opt in opt_strings:
        if "=" in opt:
            key, val = opt.split("=", 1)
            key = key.strip()
            val = val.strip()
            # Try type coercion
            if val.lower() == "true":
                result[key] = True
            elif val.lower() == "false":
                result[key] = False
            else:
                try:
                    result[key] = int(val)
                except ValueError:
                    try:
                        result[key] = float(val)
                    except ValueError:
                        result[key] = val
        else:
            # No "=" → treat as boolean flag
            result[opt.strip()] = True
    return result
