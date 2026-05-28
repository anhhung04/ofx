"""Durable execution checkpoint helpers."""

from __future__ import annotations

import hashlib
import time
from contextlib import suppress
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


def durable_dir(output_path: Path) -> Path:
    path = output_path / DURABLE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _registry_key(output_path: Path, config: DurableRunConfig) -> str:
    return f"{output_path.resolve().as_posix()}::{config.backend}"


def _resolve_redis_prefix(output_path: Path, config: DurableRunConfig) -> str:
    digest = hashlib.sha1(
        output_path.as_posix().encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:12]
    prefix = config.redis_prefix.rstrip(":")
    return f"{prefix}:{digest}:"


def _get_registry(output_path: Path, config: DurableRunConfig) -> RegistryAdapter:
    key = _registry_key(output_path, config)
    if key in _registry_cache:
        return _registry_cache[key]

    if config.backend == "redis":
        registry = RegistryFactory.create(
            "redis",
            host="localhost",
            port=6379,
            db=0,
            prefix=_resolve_redis_prefix(output_path, config),
        )
    else:
        registry_path = durable_dir(output_path) / _CHECKPOINTS_FILENAME
        registry = FileRegistry(filepath=registry_path)

    _registry_cache[key] = registry
    return registry


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
    registry = _get_registry(output_path, config)
    data = await registry.get_all()
    return list(data.values())


async def find_running_checkpoints(
    output_path: Path, config: DurableRunConfig
) -> list[dict[str, Any]]:
    checkpoints = await list_checkpoints(output_path, config)
    return [
        checkpoint for checkpoint in checkpoints if checkpoint.get("status") == "running"
    ]


async def clean_checkpoints(
    output_path: Path,
    config: DurableRunConfig,
    *,
    status: str | list[str] | None = None,
    older_than_seconds: float | None = None,
) -> int:
    """Remove checkpoints matching the given criteria."""
    registry = _get_registry(output_path, config)
    all_data = await registry.get_all()

    if not all_data:
        return 0

    statuses: set[str] | None = None
    if status is not None:
        statuses = {status} if isinstance(status, str) else set(status)

    cutoff: float | None = None
    if older_than_seconds is not None:
        cutoff = time.time() - older_than_seconds

    to_remove: list[str] = []
    for key, checkpoint in all_data.items():
        if statuses and checkpoint.get("status") not in statuses:
            continue
        if cutoff is not None:
            finished_at = checkpoint.get("finished_at")
            if finished_at:
                with suppress(ValueError, TypeError):
                    ts = datetime.fromisoformat(finished_at).timestamp()
                    if ts > cutoff:
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
    all_data = await registry.get_all()
    count = len(all_data)
    if count:
        await registry.clear()
    return count


__all__ = [
    "DURABLE_DIR_NAME",
    "clean_all_checkpoints",
    "clean_checkpoints",
    "clean_stale_checkpoints",
    "durable_dir",
    "find_running_checkpoints",
    "get_checkpoint",
    "list_checkpoints",
    "write_checkpoint",
]
