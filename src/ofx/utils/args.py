"""Argument parsing utilities."""

import json
import logging
from contextlib import suppress
from typing import Any

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

def parse_key_value_pairs(
    inputs: list[str] | None, keep_string=False
) -> dict[str, Any]:
    """Parse key=value string inputs into a dictionary.

    Supports multiple values for the same key (creates list) and JSON value parsing.

    Args:
        inputs: List of strings in "key=value" format
    Returns:
        Dictionary of parsed inputs
    Raises:
        ValueError: If input format is invalid
    """
    processed_inputs: dict[str, Any] = {}
    for inp in inputs or []:
        try:
            key, value = inp.split("=", 1)
        except ValueError:
            raise ValueError(
                f"Invalid input format: {inp}. Expected key=value."
            ) from None
        if not keep_string:
            with suppress(json.JSONDecodeError):
                value = json.loads(value)

        if key not in processed_inputs:
            processed_inputs[key] = [value]
        else:
            processed_inputs[key].append(value)

    for key in processed_inputs:
        if len(processed_inputs[key]) == 1:
            processed_inputs[key] = processed_inputs[key][0]

    logger.debug(f"Processed inputs: {processed_inputs}")
    return processed_inputs
