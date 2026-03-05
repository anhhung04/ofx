"""Business-hours awareness and random sleep helpers."""

from __future__ import annotations

import random
from datetime import UTC, datetime

__all__ = [
    "is_business_hours",
    "random_sleep_seconds",
]


def is_business_hours(
    tz_offset: int = 0,
    start: int = 9,
    end: int = 17,
    *,
    include_weekends: bool = False,
) -> bool:
    """Return True if the current UTC time (adjusted by *tz_offset* hours) is within business hours.

    Args:
        tz_offset: Hours to add to UTC to reach the target timezone.
        start: First hour (inclusive) of business hours.
        end: Last hour (exclusive) of business hours.
        include_weekends: If True, weekends count as business days.
    """
    now = datetime.now(tz=UTC)
    adjusted_hour = (now.hour + tz_offset) % 24
    day_shift = (now.hour + tz_offset) // 24
    weekday = (now.weekday() + day_shift) % 7
    is_weekday = include_weekends or weekday < 5
    return is_weekday and start <= adjusted_hour < end


def random_sleep_seconds(min_s: float, max_s: float) -> float:
    """Return a random sleep duration between *min_s* and *max_s* seconds."""
    return random.uniform(min_s, max_s)
