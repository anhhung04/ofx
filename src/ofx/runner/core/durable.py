"""Durable execution checkpoint helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ofx.models.config import DurableRunConfig
from ofx.runner.registry import RegistryAdapter
from ofx.runner.registry.factory import RegistryFactory
from ofx.runner.registry.file import FileRegistry
from ofx.settings import settings

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
    digest = hashlib.sha1(output_path.as_posix().encode("utf-8")).hexdigest()[:12]
    prefix = config.redis_prefix.rstrip(":")
    return f"{prefix}:{digest}:"


def _get_registry(output_path: Path, config: DurableRunConfig) -> RegistryAdapter:
    key = _registry_key(output_path, config)
    if key in _registry_cache:
        return _registry_cache[key]

    if config.backend == "redis":
        registry = RegistryFactory.create_redis(
            config=settings.registry_redis,
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
        checkpoint
        for checkpoint in checkpoints
        if checkpoint.get("status") == "running"
    ]
