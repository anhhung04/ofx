"""Service that encapsulates all cloud‑provider provisioning steps.

This service isolates the heavy cloud‑provider logic from the runner, making it
easier to test (the provider can be mocked) and follows the composition‑over‑
inheritance principle.
"""

from __future__ import annotations

from typing import Any

from ofx.cloud.base import CloudProvider
from ofx.cloud.runtime import build_provider_kwargs, create_remote_runner, is_windows_config
from ofx.models.cloud import CloudConfig
from ofx.utils.tempfiles import remote_work_dir


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
        from ofx.runner.logging import get_logger

        logger = get_logger()
        provider_name = cfg.provider or "static"
        provider = self._provider_registry.create(
            provider_name,
            **build_provider_kwargs(cfg),
        )
        instance = await provider.create_instance(cfg)
        if provider_name != "static":
            logger.info(
                "Waiting for instance '%s'[%s] to be ready...",
                instance.name,
                instance.instance_id,
            )
            instance = await provider.wait_until_ready(
                instance.instance_id,
                timeout=cfg.startup_timeout or 300,
            )
            refreshed = await provider.get_instance(instance.instance_id)
            if refreshed and refreshed.ip:
                instance = refreshed

        if instance and instance.ip:
            instance_ip = instance.ip
        else:
            raise RuntimeError(
                "Cloud instance has no IP address "
                f"(provider={provider_name}, instance_id={getattr(instance, 'instance_id', 'unknown')})"
            )

        from ofx.cloud.ssh import wait_for_connectivity, wait_for_login

        is_windows = is_windows_config(cfg)
        await wait_for_connectivity(
            host=instance_ip,
            ssh_port=cfg.ssh_port or 22,
            winrm_port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
            timeout=cfg.boot_timeout or 180,
            os_type="windows" if is_windows else "linux",
        )
        await wait_for_login(host=instance_ip, cfg=cfg, timeout=cfg.login_timeout)

        remote_runner = create_remote_runner(cfg, instance_ip, log_path=None, max_retries=3)
        work_dir = remote_work_dir(
            instance.instance_id,
            is_windows=is_windows_config(cfg),
        )
        return provider, instance, remote_runner, work_dir

    async def destroy(self, provider: CloudProvider, instance: Any) -> None:
        """Destroy a cloud instance (no‑op for static providers)."""
        if provider is None or instance is None:
            return
        if (instance.provider or "static") == "static":
            return
        await provider.destroy_instance(instance.instance_id)
