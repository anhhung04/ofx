"""Focused tests for registry factory helper behavior."""

from __future__ import annotations

import pytest

from ofx import runner as runner_module
from ofx.runner.registry import RegistryFactory, cleanup_registry


class _SecretValue:
    def __init__(self, value):
        self._value = value

    def get_secret_value(self):
        return self._value


def test_supported_backends_lists_registered_backends():
    assert "memory" in RegistryFactory.supported_backends()


def test_runner_create_registry_reexports_registry_factory_create():
    captured: list[tuple[str, dict[str, object]]] = []

    original_create = runner_module.RegistryFactory.create
    runner_module.RegistryFactory.create = lambda backend="memory", **config: captured.append((backend, config)) or "registry"
    try:
        assert runner_module.create_registry(backend="file", filepath="/tmp/x") == "registry"
    finally:
        runner_module.RegistryFactory.create = original_create

    assert captured == [("file", {"filepath": "/tmp/x"})]


def test_create_rejects_unsupported_backend_with_supported_backends_listed():
    with pytest.raises(ValueError, match="Unsupported registry backend: nope") as exc_info:
        RegistryFactory.create("nope")

    assert "memory" in str(exc_info.value)
    assert "file" in str(exc_info.value)


def test_create_normalizes_password_variants(monkeypatch):
    captured: list[dict[str, object]] = []

    class _Backend:
        def __init__(self, **config):
            captured.append(dict(config))

    monkeypatch.setitem(RegistryFactory._backends, "test", _Backend)

    RegistryFactory.create("test", password=None, host="x")
    RegistryFactory.create("test", password=_SecretValue("secret"))
    RegistryFactory.create("test", password=_SecretValue(None))
    RegistryFactory.create("test", password="plain")

    assert captured == [
        {"host": "x"},
        {"password": "secret"},
        {},
        {"password": "plain"},
    ]

@pytest.mark.asyncio
async def test_cleanup_registry_logs_registry_type_on_close_error(monkeypatch):
    messages: list[tuple[str, str]] = []

    class _Registry:
        async def close(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "ofx.runner.registry.logger.error",
        lambda fmt, name, exc: messages.append((fmt, f"{name}:{exc}")),
    )

    await cleanup_registry(_Registry())

    assert messages == [("Error cleaning up %s: %s", "_Registry:boom")]
