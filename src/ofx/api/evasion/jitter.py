"""Timing jitter helpers."""

from __future__ import annotations

import random
import time

__all__ = ["jitter_delay", "sleep_with_jitter"]


def jitter_delay(
    base_seconds: float,
    jitter_pct: float = 0.2,
    *,
    rng: random.Random | None = None,
) -> float:
    """Return a delay with +/- jitter.

    Args:
        base_seconds: Base delay in seconds
        jitter_pct: Fractional jitter (0.2 => +/-20%)
        rng: Optional RNG for deterministic tests
    """
    rng = rng or random
    spread = max(0.0, float(jitter_pct))
    base = max(0.0, float(base_seconds))
    if spread == 0.0:
        return base
    delta = base * spread
    return max(0.0, rng.uniform(base - delta, base + delta))


def sleep_with_jitter(base_seconds: float, jitter_pct: float = 0.2) -> float:
    """Sleep for a jittered interval and return the actual delay."""
    delay = jitter_delay(base_seconds, jitter_pct)
    time.sleep(delay)
    return delay
