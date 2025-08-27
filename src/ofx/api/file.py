from pathlib import Path


def write_file(content: str, path: Path | str) -> None:
    """Write content to a file, creating parent directories if needed."""
    if isinstance(path, str):
        path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def read_file(path: Path | str) -> str:
    """Read content from a file."""
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text()
