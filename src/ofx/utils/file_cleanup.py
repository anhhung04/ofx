"""Small filesystem cleanup helpers shared across OFX modules."""

from __future__ import annotations

import shutil
from contextlib import suppress
from pathlib import Path
from typing import Callable, Sequence

def _clear_sequence(values: list[Path] | list[str] | None) -> None:
    if values is not None:
        values.clear()

def _path_matches_required_substring(path: Path, required_substring: str | None) -> bool:
    return not required_substring or required_substring in str(path)

def remove_file(
    path_value: str | Path | None,
    *,
    required_substring: str | None = None,
) -> Exception | None:
    """Best-effort unlink with optional path marker gating."""
    if not path_value:
        return None

    if hasattr(path_value, "unlink") and not isinstance(path_value, (str, Path)):
        try:
            path_value.unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            return exc
        return None

    try:
        path = Path(path_value)
    except (TypeError, ValueError) as exc:
        return exc

    if not _path_matches_required_substring(path, required_substring):
        return None

    try:
        path.unlink(missing_ok=True)
    except (OSError, ValueError) as exc:
        return exc
    return None

def remove_tree(
    path: Path | None,
    *,
    on_error: Callable[[str], None],
    label: str,
) -> None:
    """Best-effort recursive directory removal with caller-owned logging."""
    if not path or not path.exists():
        return

    try:
        shutil.rmtree(path)
    except Exception as exc:
        on_error(f"Failed to clean up {label} {path}: {exc}")

def remove_empty_dirs(root: Path | None) -> None:
    """Remove empty directories bottom-up under *root*, including *root*."""
    if root is None or not root.is_dir():
        return

    for child in sorted(root.rglob("*"), reverse=True):
        if child.is_dir():
            with suppress(OSError):
                child.rmdir()
    with suppress(OSError):
        root.rmdir()

def remove_files_and_parent_dir(
    paths: Sequence[Path],
    *,
    on_error: Callable[[str], None],
    file_label: str,
    dir_label: str,
    clear: list[Path] | None = None,
) -> None:
    """Remove tracked files and then their shared parent directory if empty."""
    if not paths:
        _clear_sequence(clear)
        return

    parent_dir: Path | None = None
    for path in paths:
        try:
            if path.exists():
                if parent_dir is None:
                    parent_dir = path.parent
                path.unlink()
        except OSError as exc:
            on_error(f"Failed to remove {file_label} {path}: {exc}")

    if parent_dir is not None:
        try:
            parent_dir.rmdir()
        except OSError as exc:
            on_error(f"Failed to remove {dir_label} {parent_dir}: {exc}")

    _clear_sequence(clear)

def remove_files(
    paths: Sequence[str | Path],
    *,
    on_error: Callable[[str], None] | None = None,
    clear: list[str] | list[Path] | None = None,
) -> None:
    """Best-effort removal for a list of file paths."""
    for path_value in paths:
        exc = remove_file(path_value)
        if exc is not None and on_error is not None:
            on_error(f"Failed to remove file {path_value}: {exc}")

    _clear_sequence(clear)

__all__ = [
    "remove_empty_dirs",
    "remove_file",
    "remove_files",
    "remove_files_and_parent_dir",
    "remove_tree",
]
