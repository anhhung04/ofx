"""Shared cloud runtime helpers for runner/session execution paths."""

from __future__ import annotations

from typing import Any


def build_provider_kwargs(cfg: Any) -> dict[str, Any]:
    """Build kwargs for ``CloudProviderRegistry.create()`` from cloud config."""
    kwargs: dict[str, Any] = {}
    provider = cfg.provider or "static"

    if provider == "static":
        kwargs["host"] = getattr(cfg, "host", "") or ""
        kwargs["user"] = cfg.ssh_user or "root"
        kwargs["port"] = cfg.ssh_port or 22
        if cfg.ssh_key:
            kwargs["identity_file"] = cfg.ssh_key
        if cfg.ssh_password:
            kwargs["password"] = cfg.ssh_password
    elif provider == "digitalocean":
        token = (cfg.extra or {}).get("token") if hasattr(cfg, "extra") else None
        if not token and hasattr(cfg, "__pydantic_extra__"):
            token = (cfg.__pydantic_extra__ or {}).get("token")
        if token:
            kwargs["token"] = token
    elif provider == "aws":
        extras: dict[str, Any] = {}
        if hasattr(cfg, "extra"):
            extras = cfg.extra or {}
        elif hasattr(cfg, "__pydantic_extra__"):
            extras = cfg.__pydantic_extra__ or {}
        for key in ("aws_access_key_id", "aws_secret_access_key", "region_name"):
            val = extras.get(key)
            if val:
                kwargs[key] = val
        kwargs["region"] = cfg.region or "us-east-1"

    return kwargs


def create_remote_runner(
    cfg: Any,
    ip: str,
    *,
    log_path: str | None = None,
    max_retries: int = 3,
) -> Any:
    """Create PostSSH/PostWinRM runner using shared cloud config conventions."""
    from ofx.api.post import RunnerRegistry

    is_windows = (
        getattr(cfg, "connection_type", "") == "winrm"
        or (getattr(cfg, "os", "linux") or "linux") == "windows"
    )

    if is_windows:
        return RunnerRegistry.create(
            "winrm",
            host=ip,
            username=cfg.winrm_user or "Administrator",
            password=cfg.winrm_password or cfg.ssh_password or "",
            ssl=cfg.winrm_ssl or False,
            port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
            transport=getattr(cfg, "winrm_transport", "ntlm") or "ntlm",
            opsec_mode=getattr(cfg, "opsec_mode", False) or False,
            log_commands=getattr(cfg, "log_commands", False) or False,
            log_path=log_path,
        )

    return RunnerRegistry.create(
        "ssh",
        host=ip,
        user=cfg.ssh_user or "root",
        port=cfg.ssh_port or 22,
        identity_file=cfg.ssh_key or None,
        password=cfg.ssh_password or None,
        opsec_mode=getattr(cfg, "opsec_mode", False) or False,
        log_commands=getattr(cfg, "log_commands", False) or False,
        max_retries=max_retries,
        log_path=log_path,
    )
