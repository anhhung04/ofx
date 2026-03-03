"""Loot collection helpers (paths and quick parsers)."""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["find_minidumps", "list_browser_profiles", "load_json_lines"]


def find_minidumps(root: str | Path) -> list[Path]:
    base = Path(root).expanduser().resolve()
    if not base.exists():
        return []
    return sorted(base.rglob("*.dmp"))


def list_browser_profiles(root: str | Path) -> list[Path]:
    base = Path(root).expanduser().resolve()
    if not base.exists():
        return []
    patterns = [
        "**/Default/Login Data",
        "**/Default/Cookies",
        "**/User Data/*/Login Data",
        "**/User Data/*/Cookies",
    ]
    hits: list[Path] = []
    for pattern in patterns:
        hits.extend(base.glob(pattern))
    return sorted(set(hits))


def load_json_lines(path: str | Path) -> list[dict]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    records: list[dict] = []
    with file_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records
