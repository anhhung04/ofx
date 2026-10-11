"""Build a .pre-commit-config.yaml and install hooks when pre-commit is present."""

from __future__ import annotations

import pathlib
import subprocess

import yaml

_HOOK_TYPES = {
    "pre-commit": ["pre-commit"],
    "pre-push": ["pre-push"],
    "all": ["pre-commit", "pre-push"],
}


def _gitleaks_repo(gitleaks_config: str) -> dict:
    args = ["--verbose"]
    if gitleaks_config:
        args += ["--config", gitleaks_config]
    return {
        "repo": "https://github.com/gitleaks/gitleaks",
        "rev": "v8.18.0",
        "hooks": [{"id": "gitleaks", "args": args}],
    }


def _trufflehog_repo() -> dict:
    return {
        "repo": "https://github.com/trufflesecurity/trufflehog",
        "rev": "v3.67.0",
        "hooks": [{"id": "trufflehog", "args": ["--no-update"]}],
    }


def _merge_repos(existing: dict, desired: list[dict]) -> list[dict]:
    """Merge the desired hook repos into an existing pre-commit config."""
    existing_repos = existing.get("repos") if isinstance(existing, dict) else None
    repos = [item for item in existing_repos or [] if isinstance(item, dict)]
    positions = {
        item.get("repo"): index
        for index, item in enumerate(repos)
        if item.get("repo")
    }
    for repo in desired:
        index = positions.get(repo["repo"])
        if index is None:
            positions[repo["repo"]] = len(repos)
            repos.append(repo)
        else:
            repos[index] = repo
    return repos


def run(ctx):
    repo_root = pathlib.Path(str(ctx.inputs.get("repo_root", "")).strip() or ".")
    if not repo_root.is_dir():
        raise RuntimeError(f"repository root not found: {repo_root}")

    scan_mode = str(ctx.inputs.get("scan_mode", "pre-commit")).strip().lower()
    if scan_mode not in _HOOK_TYPES:
        raise ValueError(
            f"unsupported scan_mode {scan_mode!r} for hook installation; expected one "
            f"of: {', '.join(sorted(_HOOK_TYPES))}"
        )
    gitleaks_config = str(ctx.inputs.get("gitleaks_config", "")).strip()

    config_path = repo_root / ".pre-commit-config.yaml"
    existing: dict = {}
    if config_path.is_file():
        try:
            loaded = yaml.safe_load(config_path.read_text()) or {}
        except yaml.YAMLError as exc:
            raise RuntimeError(
                f"existing pre-commit config {config_path} is not valid YAML: {exc}"
            ) from exc
        if isinstance(loaded, dict):
            existing = loaded

    merged = dict(existing)
    merged["repos"] = _merge_repos(
        existing,
        [_gitleaks_repo(gitleaks_config), _trufflehog_repo()],
    )
    config_path.write_text(
        yaml.dump(merged, default_flow_style=False, sort_keys=False)
    )
    print(f"Pre-commit config written: {config_path}")

    hook_types = _HOOK_TYPES[scan_mode]
    for hook_type in hook_types:
        try:
            subprocess.run(
                ["pre-commit", "install", "--hook-type", hook_type],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "pre-commit is not installed; run: pip install pre-commit"
            ) from exc

    hooks_installed = len(hook_types)
    ctx.add_outputs(
        hooks_installed=str(hooks_installed),
        config_path=str(config_path),
    )
    print(
        f"Pre-commit hooks installed: {hooks_installed} ({', '.join(hook_types)})"
    )
