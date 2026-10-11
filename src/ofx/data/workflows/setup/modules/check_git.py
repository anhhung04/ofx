"""Detect repository state: git-ness, branch, root, and pre-commit config."""

from __future__ import annotations

import pathlib
import subprocess


def _git(repo_path: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=args, returncode=127, stdout="", stderr="git not found"
        )


def run(ctx):
    repo_path = (
        pathlib.Path(str(ctx.inputs.get("repo_path", "")).strip() or ".").expanduser().resolve()
    )
    is_git = False
    repo_root = repo_path
    default_branch = "main"
    has_precommit = False

    toplevel = _git(repo_path, "rev-parse", "--show-toplevel")
    if toplevel.returncode == 0 and toplevel.stdout.strip():
        is_git = True
        repo_root = pathlib.Path(toplevel.stdout.strip())

    if is_git:
        branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch and branch != "HEAD":
            default_branch = branch
        has_precommit = (repo_root / ".pre-commit-config.yaml").is_file()

    ctx.add_outputs(
        is_git_repo=str(is_git).lower(),
        default_branch=default_branch,
        repo_root=str(repo_root),
        has_precommit_config=str(has_precommit).lower(),
    )
    print(f"Git repo: {is_git}")
    print(f"Repository root: {repo_root}")
    print(f"Branch: {default_branch}")
    print(f"Pre-commit config exists: {has_precommit}")
