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
    """

    def __init__(self, channels_dir: str | Path | None = None) -> None:
        if channels_dir is None:
            channels_dir = Path(settings.channels_dir)
        self._dir = Path(channels_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        # Per-channel mtime cache: channel → (mtime, parsed_value)
        self._cache: dict[str, tuple[float, Any]] = {}
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
    # Low-level I/O with flock
    # ------------------------------------------------------------------

    def _write(self, channel: str, value: Any) -> None:
        """Write *value* as JSON under an exclusive flock."""
        data_path = self._channel_path(channel)
        lock_path = self._lock_path(channel)

        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            data_path.write_text(json.dumps(value, default=str))
            # Update cache immediately
            mtime = data_path.stat().st_mtime
            self._cache[channel] = (mtime, value)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

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
