"""Fetching and caching remote GitHub modules.

Remote module specs (``<owner>.<repo>.<module>[@<ref>][::<func>]``) are
cloned from ``https://github.com/<owner>/<repo>`` into the local module
cache (``~/.ofx/modules/<owner>/<repo>[@<ref>]``) on first use, then
resolved through the repo's ``ofx-modules.yml`` manifest.

Security note: remote modules are arbitrary code. OFX is a red team tool
and runs whatever the referenced repo publishes — only use repos you trust.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import git
import yaml
from filelock import FileLock
from git.exc import GitCommandError

from ofx.modules.refs import REMOTE_KIND, ModuleRef
from ofx.settings import MODULES_DIR, get_github_token

MANIFEST_FILENAME = "ofx-modules.yml"
DEFAULT_REMOTE_FUNCTION = "run"


class ManifestError(ValueError):
    """Raised when a remote module repo has a missing or invalid manifest."""


@dataclass(frozen=True, slots=True)
class RemoteModuleEntry:
    """Resolved entry point for a remote module.

    A manifest entry with an ``api:`` key resolves to an ``ofx.api`` function
    instead of a file: ``file`` is ``None`` and ``api_path`` holds the dotted
    path under ``ofx.api`` (whose last segment names the function).
    """

    file: Path | None = None
    function: str = DEFAULT_REMOTE_FUNCTION
    api_path: str | None = None


def _authenticated_url(source: str) -> str:
    """Inject a GitHub token into HTTPS clone URLs for private repo access.

    Mirrors ``ofx.collections.manager.CollectionManager._authenticated_url``
    (duplicated locally to avoid a cross-package import of a private member).
    """
    token = get_github_token()
    if not token:
        return source
    if source.startswith("https://github.com/"):
        return source.replace(
            "https://github.com/",
            f"https://x-access-token:{token}@github.com/",
            1,
        )
    return source


def cache_dir_for(ref: ModuleRef) -> Path:
    """Return the local cache directory for a remote module ref.

    Unpinned refs cache under ``MODULES_DIR/<owner>/<repo>``; pinned refs
    under ``MODULES_DIR/<owner>/<repo>@<ref>`` (one clone per ref).
    """
    if ref.kind != REMOTE_KIND:
        raise ValueError(f"Cannot cache non-remote module ref: {ref.raw!r}")
    return MODULES_DIR / ref.owner / ref.cache_key


def _clone_remote_module(ref: ModuleRef, target: Path) -> None:
    """Clone ``ref``'s repo into *target* and checkout *ref* when pinned.

    A per-target file lock prevents concurrent clones of the same repo.
    On any failure the partial clone directory is removed so a later call
    can retry cleanly.
    """
    lock = FileLock(f"{target}.lock")
    with lock:
        if target.is_dir():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        clone_url = _authenticated_url(ref.clone_url)
        try:
            repo = git.Repo.clone_from(clone_url, str(target))
        except GitCommandError as exc:
            shutil.rmtree(target, ignore_errors=True)
            raise ValueError(
                f"Failed to clone remote module '{ref.display}' from "
                f"{ref.clone_url}: {exc}"
            ) from exc
        if ref.ref:
            try:
                repo.git.checkout(ref.ref)
            except GitCommandError as exc:
                repo.close()
                shutil.rmtree(target, ignore_errors=True)
                raise ValueError(
                    f"Failed to checkout ref '{ref.ref}' for remote module "
                    f"'{ref.display}' from {ref.clone_url}: {exc}"
                ) from exc
        repo.close()


def _load_manifest(ref: ModuleRef, repo_dir: Path) -> dict:
    """Load and validate the ``ofx-modules.yml`` manifest of *repo_dir*."""
    manifest_path = repo_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ManifestError(
            f"Remote module repo '{ref.owner}/{ref.repo}' (cloned to "
            f"{repo_dir}) has no {MANIFEST_FILENAME} manifest; a manifest "
            "with a 'modules' mapping is required."
        )
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(
            f"Invalid {MANIFEST_FILENAME} in '{ref.owner}/{ref.repo}' "
            f"({manifest_path}): {exc}"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("modules"), dict):
        raise ManifestError(
            f"Invalid {MANIFEST_FILENAME} in '{ref.owner}/{ref.repo}' "
            f"({manifest_path}): expected a mapping with a 'modules' mapping."
        )
    return data


def load_manifest(ref: ModuleRef, repo_dir: Path) -> dict:
    """Load and validate the ``ofx-modules.yml`` manifest of *repo_dir*.

    Public wrapper around the internal manifest reader, used by the CLI to
    validate a freshly cloned repo.

    Raises:
        ManifestError: If the manifest is missing or invalid.
    """
    return _load_manifest(ref, repo_dir)


def _reject_api_spec_suffixes(ref: ModuleRef, module_conf: dict, repo_dir: Path) -> None:
    """Reject ``::<func>``/``function:`` on manifest ``api:`` entries.

    The function of an ``api:`` entry is the last segment of its dotted path,
    so an explicit function name would be silently ignored — fail loudly.
    """
    if ref.function:
        raise ValueError(
            f"Invalid module reference '{ref.display}': '::<func>' is not "
            f"valid for remote module '{ref.module}' — its manifest entry uses "
            f"'api: {module_conf.get('api')}' (the function is the last "
            "segment of that path)."
        )
    if module_conf.get("function"):
        raise ManifestError(
            f"Invalid {MANIFEST_FILENAME} in '{ref.owner}/{ref.repo}' "
            f"({repo_dir / MANIFEST_FILENAME}): '{ref.module}' declares both "
            f"'api: {module_conf.get('api')}' and 'function: "
            f"{module_conf.get('function')}'; an 'api' entry takes its "
            "function from the last segment of the api path."
        )


def ensure_remote_repo(ref: ModuleRef) -> Path:
    """Ensure *ref*'s repo is cached locally; return its clone directory.

    Unpinned clones are reused as-is (no auto-pull — refresh with
    ``ofx flow modules update``); pinned clones are immutable.
    """
    if ref.kind != REMOTE_KIND:
        raise ValueError(f"Cannot fetch non-remote module ref: {ref.raw!r}")
    cache_dir = cache_dir_for(ref)
    if not cache_dir.is_dir():
        _clone_remote_module(ref, cache_dir)
    return cache_dir


def ensure_remote_module(
    ref: ModuleRef, *, workflow_dir: Path | None = None
) -> RemoteModuleEntry:
    """Ensure a remote module is cached and resolve its entry file.

    ``workflow_dir`` is accepted for signature symmetry with the local
    resolvers; remote modules always cache in ``MODULES_DIR``.

    The manifest entry is either:

    - ``api: <path under ofx.api>`` — an ``ofx.api`` function (resolved
      immediately so a bad path fails fast; the repo may ship no ``.py``
      files at all); or
    - ``entry: <file>`` (default ``modules/<name>.py``) plus an optional
      ``function``, overridden by the spec's ``::<func>`` — a UDF file.

    Raises:
        ManifestError: If the repo has no valid ``ofx-modules.yml``.
        ValueError: If the module is missing from the manifest, the entry
            file is missing, or cloning/checkout failed (the message names
            owner/repo/module/ref and the attempted URL).
    """
    repo_dir = ensure_remote_repo(ref)
    data = _load_manifest(ref, repo_dir)
    modules = data.get("modules") or {}
    module_conf = modules.get(ref.module)
    if module_conf is None:
        available = ", ".join(sorted(modules)) or "(none)"
        raise ValueError(
            f"Remote module '{ref.display}' not found in manifest "
            f"{repo_dir / MANIFEST_FILENAME} (repo: {ref.clone_url}). "
            f"Available modules: {available}"
        )
    if not isinstance(module_conf, dict):
        raise ManifestError(
            f"Invalid {MANIFEST_FILENAME} in '{ref.owner}/{ref.repo}' "
            f"({repo_dir / MANIFEST_FILENAME}): entry for '{ref.module}' "
            "must be a mapping."
        )
    api_path = module_conf.get("api")
    if api_path is not None:
        if not isinstance(api_path, str) or not api_path.strip():
            raise ManifestError(
                f"Invalid {MANIFEST_FILENAME} in '{ref.owner}/{ref.repo}' "
                f"({repo_dir / MANIFEST_FILENAME}): 'api' for '{ref.module}' "
                "must be a non-empty dotted path under ofx.api, e.g. "
                "'recon.targets.split_targets'."
            )
        _reject_api_spec_suffixes(ref, module_conf, repo_dir)
        api_path = api_path.strip()
        # Imported lazily to keep the module-cache layer free of the api
        # resolver at import time; resolution fails fast on bad paths.
        from ofx.modules.api import resolve_api_callable

        resolve_api_callable(api_path)
        return RemoteModuleEntry(
            file=None,
            function=api_path.rsplit(".", 1)[-1],
            api_path=api_path,
        )
    entry = module_conf.get("entry") or f"modules/{ref.module}.py"
    entry_path = repo_dir / entry
    if not entry_path.is_file():
        raise ValueError(
            f"Remote module '{ref.display}' entry file not found: "
            f"{entry_path} (declared in manifest at "
            f"{repo_dir / MANIFEST_FILENAME}, repo: {ref.clone_url})"
        )
    function = (
        ref.function
        or module_conf.get("function")
        or DEFAULT_REMOTE_FUNCTION
    )
    return RemoteModuleEntry(file=entry_path, function=function)


def ensure_remote_module_file(
    ref: ModuleRef, *, workflow_dir: Path | None = None
) -> Path:
    """Ensure a remote module is cached and return its entry file path.

    Raises:
        ValueError: If the module is an ``api:`` manifest entry, which has no
            entry file (call :func:`ensure_remote_module` and use
            ``api_path`` instead).
    """
    entry = ensure_remote_module(ref, workflow_dir=workflow_dir)
    if entry.file is None:
        raise ValueError(
            f"Remote module '{ref.display}' is an 'api:' manifest entry "
            f"('ofx.api.{entry.api_path}') and has no entry file"
        )
    return entry.file


__all__ = [
    "DEFAULT_REMOTE_FUNCTION",
    "MANIFEST_FILENAME",
    "ManifestError",
    "RemoteModuleEntry",
    "cache_dir_for",
    "ensure_remote_module",
    "ensure_remote_module_file",
    "ensure_remote_repo",
    "load_manifest",
]
