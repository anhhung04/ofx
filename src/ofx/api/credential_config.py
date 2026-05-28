"""Small INI credential helpers for standalone API clients."""

from __future__ import annotations

import logging
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from pathlib import Path


def load_section_values(
    path: Path | None,
    section: str,
    keys: tuple[str, ...],
    *,
    logger: logging.Logger | None = None,
) -> tuple[ConfigParser, dict[str, str]]:
    """Load selected values from an INI section.

    Returns the parser too so callers can preserve unrelated sections when
    later writing credentials back to the same file.
    """
    parser = ConfigParser()
    values: dict[str, str] = {}
    if not path or not path.exists():
        return parser, values

    try:
        parser.read(path)
        if parser.has_section(section):
            values = {
                key: parser.get(section, key)
                for key in keys
                if parser.has_option(section, key)
            }
    except (OSError, ConfigParserError) as exc:
        if logger:
            logger.debug("Failed to read %s credentials from %s: %s", section, path, exc)
    return parser, values


def save_section_values(
    path: Path | None,
    parser: ConfigParser,
    section: str,
    values: dict[str, str | None],
) -> None:
    """Persist non-empty credential values in an INI section."""
    if path is None:
        return
    if not parser.has_section(section):
        parser.add_section(section)
    for key, value in values.items():
        if value is not None:
            parser.set(section, key, value)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        parser.write(f)
