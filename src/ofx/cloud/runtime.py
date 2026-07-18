"""Shared cloud runtime helpers for runner/session execution paths."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

def is_windows_config(cfg: Any) -> bool:
    return (
        getattr(cfg, "connection_type", "") == "winrm"
        or (getattr(cfg, "os", "linux") or "linux") == "windows"
    )

def remote_join(base: str, *parts: str, is_windows: bool) -> str:
    path_cls = PureWindowsPath if is_windows else PurePosixPath
    path = path_cls(str(base).rstrip("\\/"))
    for part in parts:
        path /= str(part).strip("\\/")
    return str(path)

def build_provider_kwargs(cfg: Any) -> dict[str, Any]:
    """Build kwargs for ``CloudProviderRegistry.create()`` from cloud config."""
    provider_name = cfg.provider or "static"
    extras = (
        getattr(cfg, "extra", None)
        or getattr(cfg, "__pydantic_extra__", None)
        or {}
    )

    match provider_name:
        case "static":
            kwargs = {
                "host": getattr(cfg, "host", "") or "",
                "user": cfg.ssh_user or "root",
                "port": cfg.ssh_port or 22,
            }
            if cfg.ssh_key:
                kwargs["identity_file"] = cfg.ssh_key
            if cfg.ssh_password:
                kwargs["password"] = cfg.ssh_password
            return kwargs
        case "digitalocean":
            token = extras.get("token")
            return {"token": token} if token else {}
        case "aws":
            kwargs = {
                key: value
                for key in ("aws_access_key_id", "aws_secret_access_key", "region_name")
                if (value := extras.get(key))
            }
            kwargs["region"] = cfg.region or "us-east-1"
            return kwargs
        case _:
            return {}

def create_remote_runner(
    cfg: Any,
    ip: str,
    *,
    log_path: str | None = None,
    max_retries: int = 3,
) -> Any:
    """Create PostSSH/PostWinRM runner using shared cloud config conventions."""
    from ofx.api.post import RunnerRegistry

    if is_windows_config(cfg):
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
