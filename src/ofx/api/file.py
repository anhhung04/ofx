from pathlib import Path

__all__ = ["read_file", "write_file"]

def write_file(content: str, path: Path | str) -> None:
    """Write content to a file, creating parent directories if needed.

    Args:
        content: The content to write to the file
        path: The path to write to (string or Path object)

    Example:
        write_file("Hello World", "output/test.txt")
    """
    if isinstance(path, str):
        path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def read_file(path: Path | str) -> str:
    """Read content from a file.

    Args:
        path: The path to read from (string or Path object)

    Returns:
        The contents of the file

    Example:
        content = read_file("data/input.txt")
    """
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text()
