import pytest

from ofx.runner.registry.memory import MemoryJobRegistry
from ofx.runner.registry.utils import reg_get, reg_update


@pytest.mark.asyncio
async def test_registry_utils_get_and_update() -> None:
    registry = MemoryJobRegistry()
    await registry.set("key", {"value": 1})

    value = await reg_get(registry, "key")
    assert value == {"value": 1}

    await reg_update(registry, "key", {"extra": 2})
    updated = await registry.get("key")
    assert updated == {"value": 1, "extra": 2}
