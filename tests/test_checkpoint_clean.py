"""Tests for clean checkpoint and auto-commit/push features."""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
from pathlib import Path

import pytest
import typer

from ofx.models.config import DurableRunConfig
from ofx.runner import durable as durable_store
from ofx.runner import durable_git as durable_git_module
from ofx.runner.services.checkpoint import (
    clean_all_checkpoints,
    clean_checkpoints,
    clean_stale_checkpoints,
    list_checkpoints,
    write_checkpoint,
)
from ofx.runner.durable_git import (
    auto_commit,
    auto_push,
    commit_and_push,
    is_git_repo,
)

@pytest.mark.asyncio
async def test_clean_checkpoints_by_status(tmp_path: Path) -> None:
    config = DurableRunConfig(enabled=True, resume=True, backend="file")
    await write_checkpoint(
        tmp_path, config, "cp1", {"status": "completed", "name": "a"}
    )
    await write_checkpoint(tmp_path, config, "cp2", {"status": "failed", "name": "b"})
    await write_checkpoint(
        tmp_path, config, "cp3", {"status": "completed", "name": "c"}
    )

    removed = await clean_checkpoints(tmp_path, config, status="completed")
    assert removed == 2

    remaining = await list_checkpoints(tmp_path, config)
    assert len(remaining) == 1
    assert remaining[0]["status"] == "failed"

@pytest.mark.asyncio
async def test_clean_checkpoints_by_multiple_statuses(tmp_path: Path) -> None:
    config = DurableRunConfig(enabled=True, resume=True, backend="file")
    await write_checkpoint(tmp_path, config, "cp1", {"status": "completed"})
    await write_checkpoint(tmp_path, config, "cp2", {"status": "failed"})
    await write_checkpoint(tmp_path, config, "cp3", {"status": "running"})

    removed = await clean_checkpoints(tmp_path, config, status=["completed", "failed"])
    assert removed == 2

    remaining = await list_checkpoints(tmp_path, config)
    assert len(remaining) == 1
    assert remaining[0]["status"] == "running"

@pytest.mark.asyncio
async def test_clean_stale_checkpoints(tmp_path: Path) -> None:
    config = DurableRunConfig(enabled=True, resume=True, backend="file")
    await write_checkpoint(
        tmp_path, config, "cp1", {"status": "running", "name": "stale"}
    )
    await write_checkpoint(
        tmp_path, config, "cp2", {"status": "completed", "name": "ok"}
    )

    removed = await clean_stale_checkpoints(tmp_path, config)
    assert removed == 1

    remaining = await list_checkpoints(tmp_path, config)
    assert len(remaining) == 1
    assert remaining[0]["status"] == "completed"

@pytest.mark.asyncio
async def test_clean_all_checkpoints(tmp_path: Path) -> None:
    config = DurableRunConfig(enabled=True, resume=True, backend="file")
    await write_checkpoint(tmp_path, config, "cp1", {"status": "completed"})
    await write_checkpoint(tmp_path, config, "cp2", {"status": "failed"})
    await write_checkpoint(tmp_path, config, "cp3", {"status": "running"})

    removed = await clean_all_checkpoints(tmp_path, config)
    assert removed == 3

    remaining = await list_checkpoints(tmp_path, config)
    assert len(remaining) == 0

@pytest.mark.asyncio
async def test_clean_checkpoints_by_age(tmp_path: Path) -> None:
    config = DurableRunConfig(enabled=True, resume=True, backend="file")
    await write_checkpoint(
        tmp_path,
        config,
        "old",
        {"status": "completed", "finished_at": "2020-01-01T00:00:00+00:00"},
    )
    await write_checkpoint(
        tmp_path,
        config,
        "new",
        {"status": "completed", "finished_at": "2099-01-01T00:00:00+00:00"},
    )

    removed = await clean_checkpoints(tmp_path, config, older_than_seconds=1)
    assert removed == 1

    remaining = await list_checkpoints(tmp_path, config)
    assert len(remaining) == 1
    assert remaining[0].get("finished_at", "").startswith("2099")

@pytest.mark.asyncio
async def test_clean_empty_dir(tmp_path: Path) -> None:
    config = DurableRunConfig(enabled=True, resume=True, backend="file")
    removed = await clean_checkpoints(tmp_path, config, status="completed")
    assert removed == 0

def test_get_registry_caches_by_backend_and_redis_prefix(tmp_path: Path, monkeypatch) -> None:
    durable_store._registry_cache.clear()
    first = DurableRunConfig(enabled=True, backend="redis", redis_prefix="ofx:first:")
    second = DurableRunConfig(enabled=True, backend="redis", redis_prefix="ofx:second:")
    created: list[object] = []

    monkeypatch.setattr(
        durable_store.RegistryFactory,
        "create",
        lambda _backend, **_kwargs: created.append(object()) or created[-1],
    )

    first_registry = durable_store._get_registry(tmp_path, first)
    first_registry_cached = durable_store._get_registry(tmp_path, first)
    second_registry = durable_store._get_registry(tmp_path, second)

    assert first_registry is first_registry_cached
    assert first_registry is not second_registry

def test_durable_module_all_exports_exist() -> None:
    for name in durable_store.__all__:
        assert hasattr(durable_store, name), name

def test_get_registry_builds_file_registry_for_file_backend(tmp_path: Path) -> None:
    durable_store._registry_cache.clear()
    config = DurableRunConfig(enabled=True, backend="file")

    registry = durable_store._get_registry(tmp_path, config)

    assert isinstance(registry, durable_store.FileRegistry)
    assert registry.filepath == tmp_path / ".durable" / "checkpoints.json"
    assert (tmp_path / ".durable").is_dir()

def test_get_registry_builds_redis_registry_with_resolved_prefix(tmp_path: Path, monkeypatch) -> None:
    durable_store._registry_cache.clear()
    config = DurableRunConfig(enabled=True, backend="redis", redis_prefix="ofx:test:")
    captured: list[tuple[str, dict[str, object]]] = []
    digest = hashlib.sha1(
        tmp_path.as_posix().encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]

    monkeypatch.setattr(
        durable_store.RegistryFactory,
        "create",
        lambda backend, **kwargs: captured.append((backend, kwargs)) or object(),
    )

    durable_store._get_registry(tmp_path, config)

    assert captured == [
        (
            "redis",
            {
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "prefix": f"ofx:test:{digest}:",
            },
        )
    ]

def test_durable_config_auto_commit_default() -> None:
    config = DurableRunConfig()
    assert config.auto_commit is False
    assert config.auto_push is False

def test_durable_config_auto_commit_set() -> None:
    config = DurableRunConfig(auto_commit=True, auto_push=True)
    assert config.auto_commit is True
    assert config.auto_push is True

def test_durable_config_alias() -> None:
    data = {"auto-commit": True, "auto-push": True, "enabled": True}
    config = DurableRunConfig.model_validate(data)
    assert config.auto_commit is True
    assert config.auto_push is True

def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
    )

def test_is_git_repo_false(tmp_path: Path) -> None:
    result = asyncio.run(is_git_repo(tmp_path))
    assert result is False

def test_is_git_repo_true(tmp_path: Path) -> None:
    _run_git("git", "init", cwd=tmp_path)
    result = asyncio.run(is_git_repo(tmp_path))
    assert result is True

def test_auto_commit_creates_commit(tmp_path: Path) -> None:
    _run_git("git", "init", cwd=tmp_path)
    _run_git("git", "config", "user.email", "test@test.com", cwd=tmp_path)
    _run_git("git", "config", "user.name", "Test", cwd=tmp_path)

    (tmp_path / "data.txt").write_text("hello")
    result = asyncio.run(auto_commit(tmp_path, message="test commit"))
    assert result is True

    result = _run_git("git", "log", "--oneline", cwd=tmp_path)
    assert "test commit" in result.stdout

def test_auto_commit_nothing_to_commit(tmp_path: Path) -> None:
    _run_git("git", "init", cwd=tmp_path)

    result = asyncio.run(auto_commit(tmp_path))
    assert result is False

def test_auto_commit_non_git_dir(tmp_path: Path) -> None:
    result = asyncio.run(auto_commit(tmp_path))
    assert result is False

def test_auto_push_no_remote(tmp_path: Path) -> None:
    _run_git("git", "init", cwd=tmp_path)

    result = asyncio.run(auto_push(tmp_path))
    assert result is False

def test_commit_and_push_no_action(tmp_path: Path) -> None:
    asyncio.run(commit_and_push(tmp_path, do_commit=False, do_push=False))

def test_commit_and_push_push_implies_commit(tmp_path: Path) -> None:
    _run_git("git", "init", cwd=tmp_path)
    _run_git("git", "config", "user.email", "test@test.com", cwd=tmp_path)
    _run_git("git", "config", "user.name", "Test", cwd=tmp_path)

    (tmp_path / "data.txt").write_text("hello")
    asyncio.run(commit_and_push(tmp_path, do_push=True, message="test push"))

    result = _run_git("git", "log", "--oneline", cwd=tmp_path)
    assert "test push" in result.stdout

def test_run_git_returns_timeout_tuple(monkeypatch) -> None:
    async def _run_inline(func, *args):
        return func(*args)

    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["git", "status"],
            timeout=10,
            output="partial-out\n",
            stderr="partial-err\n",
        )

    monkeypatch.setattr("asyncio.to_thread", _run_inline)
    monkeypatch.setattr(subprocess, "run", _timeout)

    rc, stdout, stderr = asyncio.run(durable_git_module._run_git(["status"], Path.cwd()))

    assert rc == 124
    assert stdout == "partial-out"
    assert stderr == "partial-err\ngit command timed out after 10s"

def test_checkpoint_list_uses_explicit_output_path(tmp_path: Path, monkeypatch) -> None:
    from ofx.commands.flow.checkpoint import checkpoint_list

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    seen: list[Path] = []
    monkeypatch.setattr("ofx.commands.get_cli_project", lambda: "globalproj")
    monkeypatch.setattr(
        "ofx.commands.project.project_manager.ProjectManager.resolve_path",
        classmethod(lambda cls, p: str(tmp_path / "other")),
    )
    async def _list_checkpoints(path, config):
        seen.append(path)
        return []

    monkeypatch.setattr("ofx.runner.services.checkpoint.list_checkpoints", _list_checkpoints)
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "ofx.commands.flow.checkpoint.print_info",
        lambda title, message: messages.append((title, message)),
    )

    checkpoint_list(output=str(explicit))

    assert seen == [explicit]
    assert messages == [("Checkpoints", "No checkpoints found.")]

def test_checkpoint_list_uses_global_cli_project(tmp_path: Path, monkeypatch) -> None:
    from ofx.commands.flow.checkpoint import checkpoint_list

    monkeypatch.setattr("ofx.commands.get_cli_project", lambda: "globalproj")
    monkeypatch.setattr(
        "ofx.commands.project.project_manager.ProjectManager.resolve_path",
        classmethod(lambda cls, p: str(tmp_path)),
    )
    seen: list[Path] = []
    async def _list_checkpoints(path, config):
        seen.append(path)
        return []

    monkeypatch.setattr("ofx.runner.services.checkpoint.list_checkpoints", _list_checkpoints)
    monkeypatch.setattr("ofx.commands.flow.checkpoint.print_info", lambda *_args: None)

    checkpoint_list(output="")

    assert seen == [tmp_path]

def test_checkpoint_show_uses_active_project(tmp_path: Path, monkeypatch) -> None:
    from ofx.commands.flow.checkpoint import checkpoint_show

    monkeypatch.setattr("ofx.commands.get_cli_project", lambda: "")
    monkeypatch.setattr(
        "ofx.commands.project.project_manager.ProjectManager.get_active_path",
        classmethod(lambda cls: tmp_path),
    )
    monkeypatch.setattr(
        "ofx.commands.project.project_manager.ProjectManager.resolve_path",
        classmethod(lambda cls, p: str(tmp_path)),
    )
    seen: list[Path] = []
    async def _list_checkpoints(path, config):
        seen.append(path)
        return []

    monkeypatch.setattr("ofx.runner.services.checkpoint.list_checkpoints", _list_checkpoints)
    monkeypatch.setattr("ofx.commands.flow.checkpoint.print_info", lambda *_args: None)

    checkpoint_show(output="")

    assert seen == [tmp_path]

def test_checkpoint_clean_without_project_raises(monkeypatch) -> None:
    from ofx.commands.flow.checkpoint import checkpoint_clean

    monkeypatch.setattr("ofx.commands.get_cli_project", lambda: "")
    monkeypatch.setattr(
        "ofx.commands.project.project_manager.ProjectManager.get_active_path",
        classmethod(lambda cls: None),
    )
    with pytest.raises(typer.BadParameter, match="No output directory"):
        checkpoint_clean(output="")

def test_checkpoint_clean_invalid_older_than_raises(tmp_path: Path) -> None:
    from ofx.commands.flow.checkpoint import checkpoint_clean

    async def _list_checkpoints(path, config):
        return [{"status": "completed"}]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ofx.runner.services.checkpoint.list_checkpoints", _list_checkpoints)
        with pytest.raises(typer.BadParameter, match="Invalid age format"):
            checkpoint_clean(output=str(tmp_path), older_than="bad-age")
