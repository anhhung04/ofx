"""Per-channel file-backed store with flock-based cross-process locking.

Each channel is a single file under ``<channels_dir>/<channel_name>``.
Locking uses POSIX ``flock`` (via :pyfunc:`fcntl.flock`) so the *same* lock
is visible to **both** Python and Bash processes — avoiding race conditions
when a ``script:`` step (Python) and a ``run:`` step (Bash) publish/subscribe
to the same channel concurrently.

Bash helpers (``ofx_publish``, ``ofx_subscribe``, ``ofx_wait_for``) are
injected into shell commands and use the same file + ``flock`` mechanism.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

ChannelValue = str | int | float | bool | list | dict | None


class ChannelStore:
    """Fast per-channel file store with cross-process flock locking.

    Design goals
    ------------
    * **One file per channel** — concurrent jobs touching *different* channels
      never contend on the same lock.
    * **flock-based locking** — compatible with both ``fcntl.flock`` (Python)
      and the ``flock`` CLI (Bash), so mixed job types share the same lock.
    * **Primitive-friendly** — stores any JSON-serializable value, not just
      ``dict``.
    * **Mtime-based read cache** — avoids re-reading a file whose content
      hasn't changed since the last read.
    * **Async API** — non-blocking ``async_publish/async_get/async_subscribe``
      methods for use from ``asyncio`` runners.  In-process events provide
      instant notification without file polling.
    """

    def __init__(self, channels_dir: str | Path | None = None) -> None:
        if channels_dir is None:
            channels_dir = Path(settings.channels_dir)
        self._dir = Path(channels_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        # Per-channel mtime cache: channel → (mtime, parsed_value)
        self._cache: dict[str, tuple[float, Any]] = {}
        # Per-channel asyncio.Event for in-process notification
        self._events: dict[str, asyncio.Event] = {}
        logger.debug("ChannelStore initialized at %s", self._dir)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _channel_path(self, channel: str) -> Path:
        """Return the data file for *channel*."""
        return self._dir / channel

    def _lock_path(self, channel: str) -> Path:
        """Return the lock file for *channel* (same dir, ``.lock`` suffix)."""
        return self._dir / f"{channel}.lock"

    # ------------------------------------------------------------------
    # In-process event helpers
    # ------------------------------------------------------------------

    def _get_event(self, channel: str) -> asyncio.Event:
        """Return (or create) an asyncio.Event for *channel*."""
        event = self._events.get(channel)
        if event is None:
            event = asyncio.Event()
            self._events[channel] = event
        return event

    def _notify(self, channel: str) -> None:
        """Signal in-process subscribers that *channel* was updated."""
        event = self._events.get(channel)
        if event is not None:
            event.set()

    # ------------------------------------------------------------------
    # Low-level I/O with flock
    # ------------------------------------------------------------------

    def _write(self, channel: str, value: Any) -> None:
        """Write *value* as JSON under an exclusive flock."""
        data_path = self._channel_path(channel)
        lock_path = self._lock_path(channel)

        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                json_text = json.dumps(value, default=str)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Failed to serialize channel '{channel}' data: {exc}") from exc
            data_path.write_text(json_text)
            # Update cache immediately
            mtime = data_path.stat().st_mtime
            self._cache[channel] = (mtime, value)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

        # Wake in-process subscribers
        self._notify(channel)

    def _read(self, channel: str) -> Any | None:
        """Read the channel value under a shared flock, using mtime cache."""
        data_path = self._channel_path(channel)
        if not data_path.exists():
            return None

        # Fast-path: mtime unchanged → return cached value
        try:
            current_mtime = data_path.stat().st_mtime
        except OSError:
            return None

        cached = self._cache.get(channel)
        if cached is not None and cached[0] == current_mtime:
            return cached[1]

        lock_path = self._lock_path(channel)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            content = data_path.read_text()
            if not content.strip():
                return None
            value = json.loads(content)
            self._cache[channel] = (data_path.stat().st_mtime, value)
            return value
        except (json.JSONDecodeError, OSError):
            return None
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    # ------------------------------------------------------------------
    # Public API (sync — used from script processes & subscribe loops)
    # ------------------------------------------------------------------

    def publish(self, channel: str, data: ChannelValue) -> None:
        """Publish *data* to *channel* (atomic write under exclusive lock)."""
        self._write(channel, data)
        logger.debug("Channel '%s' published", channel)

    def get(self, channel: str) -> Any | None:
        """Read the latest value of *channel* (shared lock + mtime cache)."""
        return self._read(channel)

    def subscribe(self, channel: str, poll_interval: float = 0.05):
        """Yield new values from *channel* as they appear.

        This is a **blocking generator** intended for use in Python ``script:``
        steps.  It polls at *poll_interval* seconds and only yields when the
        value changes.
        """

        last_value = object()  # sentinel
        while True:
            value = self._read(channel)
            if value is not None and value != last_value:
                yield value
                last_value = value
            time.sleep(poll_interval)

    def wait_for(
        self,
        channel: str,
        condition,
        timeout: int = 60,
        poll_interval: float = 0.05,
    ):
        """Block until *condition(data)* is truthy or *timeout* expires.

        Returns the matching data value.  Raises ``TimeoutError`` on timeout.
        """
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            data = self._read(channel)
            if data is not None and condition(data):
                return data
            time.sleep(poll_interval)
        raise TimeoutError(f"Timeout waiting for channel '{channel}'")

    # ------------------------------------------------------------------
    # Async API — non-blocking variants for asyncio runners
    # ------------------------------------------------------------------

    async def async_publish(self, channel: str, data: ChannelValue) -> None:
        """Async publish *data* to *channel*.

        Offloads the blocking flock I/O to a thread so the event loop
        stays responsive.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write, channel, data)
        logger.debug("Channel '%s' async published", channel)

    async def async_get(self, channel: str) -> Any | None:
        """Async read of the latest *channel* value."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read, channel)

    async def async_subscribe(self, channel: str, poll_interval: float = 0.1):
        """Async generator that yields new values from *channel*.

        Uses in-process ``asyncio.Event`` for instant notification when
        ``async_publish`` is called from the same process, falling back to
        timed polling for cross-process updates.
        """
        event = self._get_event(channel)
        last_value = object()  # sentinel
        while True:
            # Wait for notification or poll timeout
            event.clear()
            try:
                await asyncio.wait_for(event.wait(), timeout=poll_interval)
            except TimeoutError:
                pass

            loop = asyncio.get_running_loop()
            value = await loop.run_in_executor(None, self._read, channel)
            if value is not None and value != last_value:
                yield value
                last_value = value

    async def async_wait_for(
        self,
        channel: str,
        condition,
        timeout: int = 60,
        poll_interval: float = 0.1,
    ):
        """Async version of :meth:`wait_for`.

        Uses in-process event notification for low-latency detection.
        """
        event = self._get_event(channel)
        deadline = asyncio.get_event_loop().time() + timeout
        loop = asyncio.get_running_loop()

        while True:
            data = await loop.run_in_executor(None, self._read, channel)
            if data is not None and condition(data):
                return data
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Timeout waiting for channel '{channel}'")
            event.clear()
            try:
                await asyncio.wait_for(
                    event.wait(), timeout=min(poll_interval, remaining)
                )
            except TimeoutError:
                pass

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def delete(self, channel: str) -> bool:
        """Remove a channel file and its lock."""
        removed = False
        for p in (self._channel_path(channel), self._lock_path(channel)):
            try:
                p.unlink()
                removed = True
            except FileNotFoundError:
                pass
        self._cache.pop(channel, None)
        self._events.pop(channel, None)
        return removed

    def list_channels(self) -> list[str]:
        """Return names of all existing channels."""
        return [
            p.name
            for p in self._dir.iterdir()
            if p.is_file() and not p.name.endswith(".lock")
        ]

    def clear(self) -> None:
        """Remove all channels."""
        for p in self._dir.iterdir():
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        self._cache.clear()
        self._events.clear()

    def close(self) -> None:
        """Clear all channels and remove the channels directory."""
        self.clear()
        try:
            self._dir.rmdir()
            logger.debug("Removed channels directory %s", self._dir)
        except OSError:
            pass


# ------------------------------------------------------------------
# Module-level convenience (singleton per channels_dir)
# ------------------------------------------------------------------
_default_store: ChannelStore | None = None


def get_channel_store(channels_dir: str | Path | None = None) -> ChannelStore:
    """Return (or create) the default :class:`ChannelStore`."""
    global _default_store
    if _default_store is None:
        _default_store = ChannelStore(channels_dir)
    return _default_store


def close_channel_store() -> None:
    """Close and discard the default :class:`ChannelStore`."""
    global _default_store
    if _default_store is not None:
        _default_store.close()
        _default_store = None
