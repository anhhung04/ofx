"""Git helpers for durable checkpoint auto-commit and auto-push."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


async def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode(errors="replace").strip(),
        stderr.decode(errors="replace").strip(),
    )


async def is_git_repo(path: Path) -> bool:
    rc, _, _ = await _run_git(["rev-parse", "--is-inside-work-tree"], path)
    return rc == 0


async def auto_commit(output_path: Path, message: str | None = None) -> bool:
    """Stage and commit all changes under *output_path*.

    Returns True if a commit was created, False otherwise.
    """
    if not output_path.is_dir():
        return False

    if not await is_git_repo(output_path):
        logger.debug("auto-commit skipped: %s is not inside a git repository", output_path)
        return False

    rc, _, _ = await _run_git(["add", "-A", "."], output_path)
    if rc != 0:
        logger.warning("auto-commit: git add failed (rc=%d)", rc)
        return False

    rc, status_out, _ = await _run_git(["status", "--porcelain"], output_path)
    if not status_out:
        logger.debug("auto-commit: nothing to commit")
        return False

    msg = message or f"checkpoint: durable run {output_path.name}"
    rc, _, err = await _run_git(["commit", "-m", msg], output_path)
    if rc != 0:
        logger.warning("auto-commit: git commit failed: %s", err)
        return False

    logger.info("auto-commit: committed checkpoint data in %s", output_path)
    return True


async def auto_push(output_path: Path) -> bool:
    """Push the current branch to its tracked remote.

    Returns True on success, False otherwise.
    """
    if not output_path.is_dir():
        return False

    if not await is_git_repo(output_path):
        return False

    rc, remote_out, _ = await _run_git(["remote"], output_path)
    if rc != 0 or not remote_out:
        logger.debug("auto-push skipped: no git remote configured")
        return False

    remote = remote_out.splitlines()[0]
    rc, branch, _ = await _run_git(["branch", "--show-current"], output_path)
    if rc != 0 or not branch:
        logger.debug("auto-push skipped: could not determine current branch")
        return False

    rc, _, err = await _run_git(["push", remote, branch], output_path)
    if rc != 0:
        logger.warning("auto-push: git push failed: %s", err)
        return False

    logger.info("auto-push: pushed to %s/%s", remote, branch)
    return True


async def commit_and_push(
    output_path: Path,
    *,
    do_commit: bool = False,
    do_push: bool = False,
    message: str | None = None,
) -> None:
    """Perform auto-commit and/or auto-push (best-effort)."""
    if do_push:
        do_commit = True

    if not do_commit:
        return

    try:
        committed = await auto_commit(output_path, message=message)
        if committed and do_push:
            await auto_push(output_path)
    except Exception as exc:
        logger.warning("auto-commit/push failed: %s", exc)
