"""Small helpers for navigating runner parent/model relationships."""

from __future__ import annotations

from typing import Any

def runner_leaf_descendants(runner: Any) -> list[Any]:
    if runner is None:
        return []

    leaves: list[Any] = []
    stack = [runner]
    while stack:
        current = stack.pop()
        children = list(getattr(current, "_runners", {}).values())
        if not children:
            leaves.append(current)
            continue
        stack.extend(reversed(children))
    return leaves
