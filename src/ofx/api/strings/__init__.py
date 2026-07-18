"""String helpers."""

__all__ = ["remove_duplicate_string"]

def remove_duplicate_string(strings: list[str]) -> list[str]:
    """Remove duplicate strings from a list while preserving order.

    Args:
        strings: List of strings to process

    Returns:
        A new list with duplicates removed, preserving original order

    Example:
        >>> remove_duplicate_string(['a', 'b', 'a', 'c'])
        ['a', 'b', 'c']
    """
    seen = set()
    result = []
    for s in strings:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result
