"""Reliability diagnostics for OFX installations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated, Any

import typer
from rich.table import Table

from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "doctor"
HELP = "Run reliability diagnostics"


@dataclass
class CheckResult:
    name: str
    status: str  # pass, warn, fail
    detail: str


def _status_style(status: str) -> str:
    return {"pass": "green", "warn": "yellow", "fail": "red"}.get(status, "white")


def _cfg_extra(cfg: Any) -> dict[str, Any]:
    extra = getattr(cfg, "extra", None) or {}
    if extra:
        return dict(extra)
    pydantic_extra = getattr(cfg, "__pydantic_extra__", None) or {}
    return dict(pydantic_extra)


def _score_fleet_config(cfg: Any, provider_registered: bool) -> list[CheckResult]:
    checks: list[CheckResult] = []
    provider = cfg.provider or "static"

    checks.append(
        CheckResult(
            name="Provider registration",
            status="pass" if provider_registered else "fail",
            detail=provider
            if provider_registered
            else f"Unknown provider '{provider}'",
        )
    )

    extras = _cfg_extra(cfg)
    if provider == "digitalocean":
        token = extras.get("token")
        checks.append(
            CheckResult(
                name="DigitalOcean token",
                status="pass" if token else "fail",
                detail="Configured" if token else "Missing profile token",
            )
        )
    elif provider == "aws":
        access_key = extras.get("aws_access_key_id")
        secret_key = extras.get("aws_secret_access_key")
        if access_key and secret_key:
            checks.append(
                CheckResult("AWS credentials", "pass", "Access key + secret configured")
            )
        else:
            checks.append(
                CheckResult(
                    "AWS credentials",
                    "warn",
                    "No explicit keys in profile (may rely on ambient IAM credentials)",
                )
            )
    elif provider == "static":
        has_hosts = bool(getattr(cfg, "hosts", None))
        has_host = bool(getattr(cfg, "host", ""))
        checks.append(
            CheckResult(
                name="Static target host(s)",
                status="pass" if (has_host or has_hosts) else "fail",
                detail="Configured"
                if (has_host or has_hosts)
                else "Missing host/hosts",
            )
        )

    if (cfg.os or "linux") == "windows":
        checks.append(
            CheckResult(
                "WinRM credentials",
                "pass" if bool(cfg.winrm_password) else "warn",
                "Configured" if cfg.winrm_password else "No password set in profile",
            )
        )
    else:
        has_auth = bool(cfg.ssh_key or cfg.ssh_password)
        checks.append(
            CheckResult(
                "SSH auth material",
                "pass" if has_auth else "warn",
                "Configured" if has_auth else "No key/password in profile",
            )
        )

    return checks


async def _probe_connectivity(cfg: Any, host: str, timeout: int) -> list[CheckResult]:
    from ofx.cloud.ssh import wait_for_connectivity, wait_for_login

    checks: list[CheckResult] = []
    os_type = getattr(cfg, "os", "linux") or "linux"
    try:
        await wait_for_connectivity(
            host=host,
            os_type=os_type,
            ssh_port=cfg.ssh_port or 22,
            winrm_port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
            timeout=timeout,
        )
        checks.append(CheckResult("Network connectivity", "pass", f"{host} reachable"))
    except Exception as exc:
        checks.append(CheckResult("Network connectivity", "fail", str(exc)))
        return checks

    try:
        await wait_for_login(
            host=host,
            cfg=cfg,
            timeout=getattr(cfg, "login_timeout", timeout) or timeout,
        )
        checks.append(
            CheckResult("Authenticated login", "pass", "Login probe succeeded")
        )
    except Exception as exc:
        checks.append(CheckResult("Authenticated login", "fail", str(exc)))
    return checks


@app.command("workflows")
def doctor_workflows(
    check_tasks: Annotated[
        bool,
        typer.Option(
            "--check-tasks", help="Verify that referenced tasks are registered"
        ),
    ] = False,
):
    """Validate all discoverable workflows and report a health summary."""
    from ofx.commands.flow.validate import validate_workflows

    validate_workflows(all_workflows=True, check_tasks=check_tasks)


@app.command("fleet")
def doctor_fleet(
    profile: Annotated[
        str, typer.Option("--profile", "-p", help="Cloud profile to score")
    ] = "",
    host: Annotated[
        str, typer.Option("--host", help="Optional host override for live probe")
    ] = "",
    check_connectivity: Annotated[
        bool,
        typer.Option("--check-connectivity", help="Run live connectivity/login probes"),
    ] = False,
    timeout: Annotated[
        int, typer.Option("--timeout", "-t", help="Probe timeout in seconds")
    ] = 60,
):
    """Run a fleet reliability scorecard against a cloud profile."""
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager
    from ofx.models.cloud import CloudConfig

    console = get_console()
    mgr = get_cloud_profile_manager()

    profile_name = profile or mgr.default_profile_name
    if not profile_name:
        console.print(
            "[red]No profile specified and no default cloud profile set.[/red]"
        )
        raise typer.Exit(code=1)

    try:
        resolved = mgr.resolve(CloudConfig(profile=profile_name))
    except Exception as exc:
        console.print(f"[red]Failed to resolve profile '{profile_name}': {exc}[/red]")
        raise typer.Exit(code=1) from exc

    provider = resolved.provider or "static"
    provider_registered = CloudProviderRegistry.get(provider) is not None
    checks = _score_fleet_config(resolved, provider_registered)

    probe_host = host
    if not probe_host:
        if resolved.host:
            probe_host = resolved.host
        elif resolved.hosts:
            probe_host = resolved.hosts[0].host

    if check_connectivity:
        if probe_host:
            checks.extend(
                asyncio.run(_probe_connectivity(resolved, probe_host, timeout))
            )
        else:
            checks.append(
                CheckResult(
                    "Connectivity probe target",
                    "warn",
                    "No host available (set --host or use static profile host/hosts)",
                )
            )

    table = Table(title=f"Fleet Reliability Scorecard · {profile_name}")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    fails = 0
    warns = 0
    for c in checks:
        if c.status == "fail":
            fails += 1
        elif c.status == "warn":
            warns += 1
        style = _status_style(c.status)
        table.add_row(c.name, f"[{style}]{c.status.upper()}[/{style}]", c.detail)

    console.print(table)
    console.print(
        f"[bold]Summary:[/bold] pass={len(checks) - fails - warns} warn={warns} fail={fails}"
    )
    if fails:
        raise typer.Exit(code=1)
