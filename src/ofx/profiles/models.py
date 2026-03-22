"""Pydantic models for OFX profiles and time windows."""

from __future__ import annotations

from datetime import time
from typing import Any

from pydantic import BaseModel, Field


class TimeWindow(BaseModel):
    """Defines an allowed execution time window.

    If enabled, workflows will only run during the specified times/days.
    A running workflow will be aborted if the window expires mid-execution.
    """

    enabled: bool = Field(default=False, description="Activate time window enforcement")
    start: str = Field(
        default="00:00",
        description="Window start time (HH:MM, 24-hour format)",
    )
    end: str = Field(
        default="23:59",
        description="Window end time (HH:MM, 24-hour format)",
    )
    days: list[str] = Field(
        default_factory=lambda: [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ],
        description="Allowed days of the week (lowercase English names)",
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone name (e.g. 'US/Eastern', 'Europe/London')",
    )
    warn_before_minutes: int = Field(
        default=10,
        description="Minutes before window end to warn the user",
    )
    abort_on_expire: bool = Field(
        default=True,
        description="Abort running workflow when time window expires",
    )

    def start_time(self) -> time:
        """Parse start as a datetime.time object."""
        h, m = self.start.split(":")
        return time(int(h), int(m))

    def end_time(self) -> time:
        """Parse end as a datetime.time object."""
        h, m = self.end.split(":")
        return time(int(h), int(m))


class OFXProfile(BaseModel):
    """A named profile containing reusable workflow settings.

    Profiles are stored in ``~/.ofx/profiles.yml`` and referenced
    from workflows via ``defaults.profile: <name>``.
    """

    name: str = Field(default="", description="Profile display name")
    description: str = Field(default="", description="What this profile is for")

    # ── Rate & intensity controls ──────────────────────────────────
    rate_limit: int = Field(
        default=0,
        description="Max requests per minute (0 = unlimited)",
    )
    max_retries: int = Field(
        default=3,
        description="Default retry count for failing steps",
    )
    timeout_minutes: int = Field(
        default=60,
        description="Default step timeout in minutes",
    )
    threads: int = Field(
        default=10,
        description="Default thread/concurrency count for tools",
    )

    # ── Stealth / opsec ────────────────────────────────────────────
    delay: float = Field(
        default=0.0,
        description="Delay between requests in seconds",
    )
    jitter: float = Field(
        default=0.0,
        description="Random jitter added to delay (seconds)",
    )
    user_agent: str = Field(
        default="",
        description="Custom User-Agent string for HTTP tools",
    )
    proxy: str = Field(
        default="",
        description="Proxy URL (e.g. socks5://127.0.0.1:9050)",
    )

    # ── Time window ────────────────────────────────────────────────
    time_window: TimeWindow = Field(
        default_factory=TimeWindow,
        description="Allowed execution time window",
    )

    # ── Workflow-level defaults ─────────────────────────────────────
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Additional env vars injected into all jobs",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for filtering profiles",
    )

    # ── Task option overrides ──────────────────────────────────────
    task_options: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-task option overrides.  Keys are task names, values are "
            "dicts of options.  e.g. {'nmap': {'timing': 'T2'}}"
        ),
    )
