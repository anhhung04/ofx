"""Registry utility helpers for consistent access."""

from __future__ import annotations

from typing import Any

from ofx.runner.registry import RegistryAdapter


async def reg_get(registry: RegistryAdapter, key: str) -> dict[str, Any] | None:
    return await registry.get(key)


async def reg_update(registry: RegistryAdapter, key: str, updates: dict[str, Any]) -> None:
    await registry.update(key, updates)
