"""Tests for clean checkpoint and auto-commit/push features."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ofx.models.config import DurableRunConfig
from ofx.runner.core.durable import (
    clean_all_checkpoints,
    clean_checkpoints,
    clean_stale_checkpoints,
    list_checkpoints,
    write_checkpoint,
)
from ofx.runner.core.durable_git import (
    auto_commit,
    auto_push,
    commit_and_push,
    is_git_repo,
)

# ── Clean checkpoint tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_clean_checkpoints_by_status(tmp_path: Path) -> None:
    config = DurableRunConfig(enabled=True, resume=True, backend="file")
    await write_checkpoint(tmp_path, config, "cp1", {"status": "completed", "name": "a"})
    await write_checkpoint(tmp_path, config, "cp2", {"status": "failed", "name": "b"})
    await write_checkpoint(tmp_path, config, "cp3", {"status": "completed", "name": "c"})

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
    await write_checkpoint(tmp_path, config, "cp1", {"status": "running", "name": "stale"})
    await write_checkpoint(tmp_path, config, "cp2", {"status": "completed", "name": "ok"})

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


# ── DurableRunConfig model tests ──────────────────────────────────


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


# ── Git helper tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_is_git_repo_false(tmp_path: Path) -> None:
    result = await is_git_repo(tmp_path)
    assert result is False


@pytest.mark.asyncio
async def test_is_git_repo_true(tmp_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git", "init", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    result = await is_git_repo(tmp_path)
    assert result is True


@pytest.mark.asyncio
async def test_auto_commit_creates_commit(tmp_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git", "init", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    proc = await asyncio.create_subprocess_exec(
        "git", "config", "user.email", "test@test.com", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    proc = await asyncio.create_subprocess_exec(
        "git", "config", "user.name", "Test", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    (tmp_path / "data.txt").write_text("hello")
    result = await auto_commit(tmp_path, message="test commit")
    assert result is True

    proc = await asyncio.create_subprocess_exec(
        "git", "log", "--oneline", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    assert "test commit" in stdout.decode()


@pytest.mark.asyncio
async def test_auto_commit_nothing_to_commit(tmp_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git", "init", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    result = await auto_commit(tmp_path)
    assert result is False


@pytest.mark.asyncio
async def test_auto_commit_non_git_dir(tmp_path: Path) -> None:
    result = await auto_commit(tmp_path)
    assert result is False


@pytest.mark.asyncio
async def test_auto_push_no_remote(tmp_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git", "init", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    result = await auto_push(tmp_path)
    assert result is False


@pytest.mark.asyncio
async def test_commit_and_push_no_action(tmp_path: Path) -> None:
    await commit_and_push(tmp_path, do_commit=False, do_push=False)


@pytest.mark.asyncio
async def test_commit_and_push_push_implies_commit(tmp_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git", "init", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    proc = await asyncio.create_subprocess_exec(
        "git", "config", "user.email", "test@test.com", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    proc = await asyncio.create_subprocess_exec(
        "git", "config", "user.name", "Test", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    (tmp_path / "data.txt").write_text("hello")
    await commit_and_push(tmp_path, do_push=True, message="test push")

    proc = await asyncio.create_subprocess_exec(
        "git", "log", "--oneline", cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    assert "test push" in stdout.decode()
