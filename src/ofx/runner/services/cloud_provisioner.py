"""Service that encapsulates all cloud‑provider provisioning steps.

This service isolates the heavy cloud‑provider logic from the runner, making it
easier to test (the provider can be mocked) and follows the composition‑over‑
inheritance principle.
"""

from __future__ import annotations

from typing import Any

from ofx.cloud.base import CloudProvider
from ofx.models.cloud import CloudConfig


class CloudProvisioner:
    """Handles provisioning, connection, and cleanup of a cloud VPS.

    The public ``provision`` method returns a tuple ``(provider, instance,
    remote_runner, work_dir)`` which the caller can store.
    """

    def __init__(self, provider_registry):
        self._provider_registry = provider_registry

    async def provision(self, cfg: CloudConfig) -> tuple[CloudProvider, Any, Any, str]:
        """Create a VPS, wait for it to be reachable, and return the tools.

        Returns:
            provider – the concrete provider instance
            instance – the created cloud instance object
            remote_runner – a PostSSH or PostWinRM runner ready for commands
            work_dir – a temporary remote working directory path
        """
        from ofx.cloud.ssh import wait_for_connectivity, wait_for_login
        from ofx.runner.logging import get_logger

        logger = get_logger()
        provider_name = cfg.provider or "static"
        provider_kwargs = self._build_provider_kwargs(cfg)

        provider = self._provider_registry.create(provider_name, **provider_kwargs)
        instance = await provider.create_instance(cfg)

        if provider_name != "static":
            logger.info(
                f"Waiting for instance '{instance.name}'[{instance.instance_id}] to be ready..."
            )
            instance = await provider.wait_until_ready(
                instance.instance_id, timeout=cfg.startup_timeout or 300
            )
            refreshed = await provider.get_instance(instance.instance_id)
            if refreshed and refreshed.ip:
                instance = refreshed

        if not instance or not instance.ip:
            raise RuntimeError("Instance has no IP address")

        is_windows = cfg.connection_type == "winrm"
        await wait_for_connectivity(
            host=instance.ip,
            ssh_port=cfg.ssh_port or 22,
            winrm_port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
            timeout=cfg.boot_timeout or 180,
            os_type="windows" if is_windows else "linux",
        )
        await wait_for_login(host=instance.ip, cfg=cfg, timeout=cfg.login_timeout)

        remote_runner = self._create_remote_runner(cfg, instance.ip)
        work_dir = (
            f"/tmp/.run-{instance.instance_id[:8]}"
            if not is_windows
            else f"C:\\Windows\\Temp\\.run-{instance.instance_id[:8]}"
        )
        return provider, instance, remote_runner, work_dir

    async def destroy(self, provider: CloudProvider, instance: Any) -> None:
        """Destroy a cloud instance (no‑op for static providers)."""
        if provider is None or instance is None:
            return
        if (instance.provider or "static") == "static":
            return
        await provider.destroy_instance(instance.instance_id)

    # ------------------------------------------------------------------
    # Helper methods (moved from CloudJobRunner)
    # ------------------------------------------------------------------
    @staticmethod
    def _build_provider_kwargs(cfg: CloudConfig) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        provider = cfg.provider or "static"

        if provider == "static":
            kwargs["host"] = cfg.host
            kwargs["user"] = cfg.ssh_user
            kwargs["port"] = cfg.ssh_port or 22
            if cfg.ssh_key:
                kwargs["identity_file"] = cfg.ssh_key
            if cfg.ssh_password:
                kwargs["password"] = cfg.ssh_password
        elif provider == "digitalocean":
            token = cfg.extra.get("token") if cfg.extra else None
            if token:
                kwargs["token"] = token
        elif provider == "aws":
            for key in ("aws_access_key_id", "aws_secret_access_key", "region_name"):
                val = (cfg.extra or {}).get(key)
                if val:
                    kwargs[key] = val
            kwargs["region"] = cfg.region or "us-east-1"
        return kwargs

    @staticmethod
    def _create_remote_runner(cfg: CloudConfig, ip: str):
        from ofx.api.post import RunnerRegistry

        is_windows = cfg.connection_type == "winrm"
        if is_windows:
            return RunnerRegistry.create(
                "winrm",
                host=ip,
                username=cfg.winrm_user or "Administrator",
                password=cfg.winrm_password or cfg.ssh_password or "",
                ssl=cfg.winrm_ssl or False,
                port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
                opsec_mode=cfg.opsec_mode or False,
                log_commands=cfg.log_commands or False,
                log_path=None,
            )
        return RunnerRegistry.create(
            "ssh",
            host=ip,
            user=cfg.ssh_user or "root",
            port=cfg.ssh_port or 22,
            identity_file=cfg.ssh_key,
            password=cfg.ssh_password,
            opsec_mode=cfg.opsec_mode or False,
            log_commands=cfg.log_commands or False,
            max_retries=3,
            log_path=None,
        )
