"""Detect repository state: git-ness, branch, and pre-commit config presence."""
import pathlib
import subprocess


def run(ctx):
    repo_path = pathlib.Path(str(ctx.inputs.get("repo_path", "."))).resolve()
    is_git = False
    default_branch = "main"
    has_precommit = False

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
        is_git = result.returncode == 0

        if is_git:
            branch_result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
            )
            default_branch = branch_result.stdout.strip() or "main"

            has_precommit = (repo_path / ".pre-commit-config.yaml").exists()
    except Exception:
        pass

    ctx.add_outputs(
        is_git_repo=str(is_git).lower(),
        default_branch=default_branch,
        repo_root=str(repo_path),
        has_precommit_config=str(has_precommit).lower(),
    )
    print(f"Git repo: {is_git}")
    print(f"Branch: {default_branch}")
    print(f"Pre-commit config exists: {has_precommit}")
