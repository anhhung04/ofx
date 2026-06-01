"""Low-level durable checkpoint storage helpers.

Public callers should prefer `ofx.runner.services.checkpoint`.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ofx.models.config import DurableRunConfig
from ofx.runner.registry import RegistryFactory
from ofx.runner.registry_adapter import RegistryAdapter
from ofx.runner.registry_backends.file import FileRegistry

DURABLE_DIR_NAME = ".durable"
_CHECKPOINTS_FILENAME = "checkpoints.json"
_registry_cache: dict[str, RegistryAdapter] = {}


def _get_registry(output_path: Path, config: DurableRunConfig) -> RegistryAdapter:
    key_parts = [output_path.resolve().as_posix(), config.backend]
    if config.backend == "redis":
        key_parts.append(config.redis_prefix.rstrip(":"))
    key = "::".join(key_parts)
    if key in _registry_cache:
        return _registry_cache[key]

    if config.backend == "redis":
        digest = hashlib.sha1(
            output_path.as_posix().encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:12]
        registry = RegistryFactory.create(
            "redis",
            host="localhost",
            port=6379,
            db=0,
            prefix=f"{config.redis_prefix.rstrip(':')}:{digest}:",
        )
    else:
        durable_path = output_path / DURABLE_DIR_NAME
        durable_path.mkdir(parents=True, exist_ok=True)
        registry = FileRegistry(
            filepath=durable_path / _CHECKPOINTS_FILENAME
        )
    _registry_cache[key] = registry
    return registry


async def _checkpoint_data(
    output_path: Path,
    config: DurableRunConfig,
) -> dict[str, dict[str, Any]]:
    registry = _get_registry(output_path, config)
    return await registry.get_all()


async def write_checkpoint(
    output_path: Path,
    config: DurableRunConfig,
    checkpoint_id: str,
    payload: dict[str, Any],
) -> None:
    registry = _get_registry(output_path, config)
    await registry.set(checkpoint_id, payload)


async def get_checkpoint(
    output_path: Path, config: DurableRunConfig, checkpoint_id: str
) -> dict[str, Any] | None:
    registry = _get_registry(output_path, config)
    return await registry.get(checkpoint_id)


async def list_checkpoints(
    output_path: Path, config: DurableRunConfig
) -> list[dict[str, Any]]:
    return list((await _checkpoint_data(output_path, config)).values())


async def clean_checkpoints(
    output_path: Path,
    config: DurableRunConfig,
    *,
    status: str | list[str] | None = None,
    older_than_seconds: float | None = None,
) -> int:
    """Remove checkpoints matching the given criteria."""
    registry = _get_registry(output_path, config)
    all_data = await _checkpoint_data(output_path, config)

    if not all_data:
        return 0

    statuses = None if status is None else {status} if isinstance(status, str) else set(status)
    cutoff = None if older_than_seconds is None else time.time() - older_than_seconds
    to_remove: list[str] = []
    for key, checkpoint in all_data.items():
        if statuses and checkpoint.get("status") not in statuses:
            continue
        if cutoff is not None:
            finished_at = checkpoint.get("finished_at")
            if finished_at:
                try:
                    finished_ts = datetime.fromisoformat(finished_at).timestamp()
                except (ValueError, TypeError):
                    finished_ts = None
                if finished_ts is not None and finished_ts > cutoff:
                    continue
        to_remove.append(key)

    for key in to_remove:
        await registry.delete(key)

    return len(to_remove)


async def clean_stale_checkpoints(
    output_path: Path,
    config: DurableRunConfig,
) -> int:
    return await clean_checkpoints(output_path, config, status="running")


async def clean_all_checkpoints(
    output_path: Path,
    config: DurableRunConfig,
) -> int:
    registry = _get_registry(output_path, config)
    all_data = await _checkpoint_data(output_path, config)
    count = len(all_data)
    if count:
        await registry.clear()
    return count


__all__ = [
    "DURABLE_DIR_NAME",
    "clean_all_checkpoints",
    "clean_checkpoints",
    "clean_stale_checkpoints",
    "get_checkpoint",
    "list_checkpoints",
    "write_checkpoint",
]
