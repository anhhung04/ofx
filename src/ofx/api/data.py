"""Data staging and exfil helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

__all__ = ["archive_path", "split_file"]


def archive_path(src: str | Path, *, output: str | Path | None = None, fmt: str = "zip") -> Path:
    src_path = Path(src).expanduser().resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"Source path not found: {src_path}")
    base_name = Path(output).expanduser().resolve() if output else src_path
    archive_base = str(base_name)
    archive = shutil.make_archive(archive_base, fmt, root_dir=src_path)
    return Path(archive)


def split_file(path: str | Path, *, chunk_mb: int, output_dir: str | Path | None = None) -> list[Path]:
    if chunk_mb <= 0:
        raise ValueError("chunk_mb must be positive")
    src = Path(path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"File not found: {src}")
    out_dir = Path(output_dir).expanduser().resolve() if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    src.stat().st_size
    chunk_size = chunk_mb * 1024 * 1024
    parts: list[Path] = []
    with src.open("rb") as f:
        idx = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            part = out_dir / f"{src.name}.part{idx}"
            part.write_bytes(chunk)
            parts.append(part)
            idx += 1
    return parts
