from typing import List

def remove_duplicate_string(strings: List[str]) -> List[str]:
    """Remove duplicate strings from a list while preserving order."""
    seen = set()
    result = []
    for s in strings:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result
