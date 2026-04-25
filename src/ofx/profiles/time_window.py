"""Time window enforcement for workflow execution.

Checks whether the current time is inside the allowed execution window
and provides a background task for periodic checking during long runs.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING, Any

from ofx.profiles.models import TimeWindow
from ofx.settings import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(settings.app_branding)


def _now_in_tz(tz_name: str) -> datetime:
    """Return current datetime in the specified timezone."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name))
    except (ImportError, KeyError):
        logger.warning("Timezone '%s' not available, falling back to UTC", tz_name)
        return datetime.now(UTC)


def _time_in_range(start: time, end: time, current: time) -> bool:
    """Check if *current* is between *start* and *end*.

    Handles overnight windows (e.g. 22:00 → 06:00).
    """
    if start <= end:
        return start <= current <= end
    # Overnight: e.g. start=22:00, end=06:00
    return current >= start or current <= end


def check_time_window(window: TimeWindow) -> dict[str, Any]:
    """Validate current time against the window.

    Returns a dict with:
      - ``allowed``: bool — is execution currently allowed?
      - ``remaining_minutes``: int — minutes until window closes
      - ``message``: str — human-readable status
    """
    if not window.enabled:
        return {"allowed": True, "remaining_minutes": -1, "message": ""}

    now = _now_in_tz(window.timezone)
    current_day = now.strftime("%A").lower()
    current_time = now.time()

    # Day check
    if current_day not in [d.lower() for d in window.days]:
        return {
            "allowed": False,
            "remaining_minutes": 0,
            "message": (
                f"Today ({current_day.title()}) is outside the allowed days "
                f"({', '.join(d.title() for d in window.days)})"
            ),
        }

    # Time check
    start = window.start_time()
    end = window.end_time()

    if not _time_in_range(start, end, current_time):
        return {
            "allowed": False,
            "remaining_minutes": 0,
            "message": (
                f"Current time {now.strftime('%H:%M')} {window.timezone} is outside "
                f"the allowed window ({window.start}–{window.end})"
            ),
        }

    # Calculate remaining minutes
    end_dt = now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if end < start:
        # Overnight: end is tomorrow
        from datetime import timedelta

        if current_time >= start:
            end_dt += timedelta(days=1)

    remaining = (end_dt - now).total_seconds() / 60
    remaining_minutes = max(0, int(remaining))

    msg = ""
    if 0 < remaining_minutes <= window.warn_before_minutes:
        msg = (
            f"⚠️  Only {remaining_minutes} minutes remaining in execution window "
            f"({window.start}–{window.end} {window.timezone})"
        )

    return {
        "allowed": True,
        "remaining_minutes": remaining_minutes,
        "message": msg,
    }


class TimeWindowGuard:
    """Background task that periodically checks the time window.

    Create with a :class:`TimeWindow` and call :meth:`start` to begin
    monitoring.  Call :meth:`stop` when the workflow finishes.

    If the window expires and ``abort_on_expire`` is set, the guard
    cancels the monitored asyncio task.
    """

    def __init__(
        self,
        window: TimeWindow,
        on_warn: Any | None = None,
        on_abort: Any | None = None,
        check_interval: int = 30,
    ) -> None:
        self._window = window
        self._on_warn = on_warn  # Callable[[str], None]
        self._on_abort = on_abort  # Callable[[str], None]
        self._check_interval = check_interval
        self._task: asyncio.Task | None = None
        self._warned = False
        self._abort_event = asyncio.Event()

    @property
    def should_abort(self) -> bool:
        return self._abort_event.is_set()

    def start(self) -> None:
        """Start the background monitoring task."""
        if not self._window.enabled:
            return
        self._task = asyncio.create_task(self._monitor())

    def stop(self) -> None:
        """Stop the monitoring task."""
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None

    async def _monitor(self) -> None:
        """Periodic check loop."""
        try:
            while True:
                result = check_time_window(self._window)

                if not result["allowed"]:
                    msg = f"🛑 Time window expired: {result['message']}"
                    logger.warning(msg)
                    if self._on_abort:
                        self._on_abort(msg)
                    if self._window.abort_on_expire:
                        self._abort_event.set()
                        return

                elif result["message"] and not self._warned:
                    self._warned = True
                    logger.warning(result["message"])
                    if self._on_warn:
                        self._on_warn(result["message"])

                await asyncio.sleep(self._check_interval)
        except asyncio.CancelledError:
            pass
