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
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from ofx.settings import settings
from ofx.utils.file_cleanup import remove_empty_dirs, remove_file

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
    * **Async API** — awaitable variants for ``asyncio`` runners. In-process
      events provide instant notification without file polling, while local
      channel file I/O remains small and synchronous.
    """

    def __init__(self, channels_dir: str | Path | None = None) -> None:
        if channels_dir is None:
            channels_dir = Path(settings.channels_dir)
        self._dir = Path(channels_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, tuple[int, Any]] = {}
        self._events: dict[
            str, tuple[asyncio.AbstractEventLoop | None, asyncio.Event]
        ] = {}
        logger.debug("ChannelStore initialized at %s", self._dir)

    def _get_event(self, channel: str) -> asyncio.Event:
        """Return (or create) an asyncio.Event for *channel*."""
        binding = self._events.get(channel)
        if binding is None:
            loop: asyncio.AbstractEventLoop | None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            event = asyncio.Event()
            self._events[channel] = (loop, event)
            return event
        return binding[1]

    def _notify(self, channel: str) -> None:
        """Signal in-process subscribers that *channel* was updated."""
        binding = self._events.get(channel)
        if binding is None:
            return

        loop, event = binding
        if loop is None:
            event.set()
            return

        loop.call_soon_threadsafe(event.set)

    @staticmethod
    @contextmanager
    def _locked_fd(lock_path: Path, lock_mode: int) -> Generator[int]:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, lock_mode)
            yield fd
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _read_json_value(data_path: Path) -> Any | None:
        content = data_path.read_text()
        if not content.strip():
            return None
        return json.loads(content)

    def _channel_paths(self, channel: str) -> tuple[Path, Path]:
        return self._dir / channel, self._dir / f"{channel}.lock"

    def _write(self, channel: str, value: Any) -> None:
        """Write *value* as JSON under an exclusive flock."""
        data_path, lock_path = self._channel_paths(channel)

        with self._locked_fd(lock_path, fcntl.LOCK_EX):
            try:
                json_text = json.dumps(value, default=str)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Failed to serialize channel '{channel}' data: {exc}"
                ) from exc
            data_path.write_text(json_text)
            try:
                mtime = data_path.stat().st_mtime_ns
            except OSError:
                mtime = None
            if mtime is not None:
                self._cache[channel] = (mtime, value)

        self._notify(channel)

    def _read(self, channel: str) -> Any | None:
        """Read the channel value under a shared flock, using mtime cache."""
        data_path, lock_path = self._channel_paths(channel)
        if not data_path.exists():
            return None

        try:
            current_mtime = data_path.stat().st_mtime_ns
        except OSError:
            return None

        cached = self._cache.get(channel)
        cached_value = cached[1] if cached is not None and cached[0] == current_mtime else None
        if cached_value is not None:
            return cached_value

        try:
            with self._locked_fd(lock_path, fcntl.LOCK_SH):
                value = self._read_json_value(data_path)
                try:
                    mtime = data_path.stat().st_mtime_ns
                except OSError:
                    mtime = None
                if mtime is None or value is None:
                    return value
                self._cache[channel] = (mtime, value)
                return value
        except (json.JSONDecodeError, OSError):
            return None

    def publish(self, channel: str, data: ChannelValue) -> None:
        """Publish *data* to *channel* (atomic write under exclusive lock)."""
        self._write(channel, data)
        logger.debug("Channel '%s' published", channel)

    def get(self, channel: str) -> Any | None:
        """Read the latest value of *channel* (shared lock + mtime cache)."""
        return self._read(channel)

    def subscribe(self, channel: str, poll_interval: float = 0.05) -> Generator[Any]:
        """Yield new values from *channel* as they appear.

        This is a **blocking generator** intended for use in Python ``script:``
        steps.  It polls at *poll_interval* seconds and only yields when the
        value changes.
        """

        last_value = object()
        while True:
            value = self._read(channel)
            if value is not None and value != last_value:
                yield value
                last_value = value
            time.sleep(poll_interval)

    def wait_for(
        self,
        channel: str,
        condition: Callable[[Any], bool],
        timeout: int = 60,
        poll_interval: float = 0.05,
    ) -> Any:
        """Block until *condition(data)* is truthy or *timeout* expires.

        Returns the matching data value.  Raises ``TimeoutError`` on timeout.
        """
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            data = self._read(channel)
            if data is not None:
                if condition(data):
                    return data
            time.sleep(poll_interval)
        raise TimeoutError(f"Timeout waiting for channel '{channel}'")

    async def async_publish(self, channel: str, data: ChannelValue) -> None:
        """Async publish *data* to *channel*.

        The file I/O is local and small, so it is performed inline while the
        waiting portions of the async API stay non-blocking.
        """
        self._write(channel, data)
        logger.debug("Channel '%s' async published", channel)

    async def async_get(self, channel: str) -> Any | None:
        """Async read of the latest *channel* value."""
        return self._read(channel)

    async def async_subscribe(self, channel: str, poll_interval: float = 0.1):
        """Async generator that yields new values from *channel*.

        Uses in-process ``asyncio.Event`` for instant notification when
        ``async_publish`` is called from the same process, falling back to
        timed polling for cross-process updates.
        """
        event = self._get_event(channel)
        last_value = object()
        while True:
            value = self._read(channel)
            if value is not None and value != last_value:
                yield value
                last_value = value
                continue

            event.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(event.wait(), timeout=poll_interval)

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
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            data = self._read(channel)
            if data is not None:
                if condition(data):
                    return data
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"Timeout waiting for channel '{channel}'")
            event.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(event.wait(), timeout=min(poll_interval, remaining))

    def delete(self, channel: str) -> bool:
        """Remove a channel file and its lock."""
        removed = False
        for path in self._channel_paths(channel):
            existed = path.exists()
            if remove_file(path) is None and existed and not path.exists():
                removed = True
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
        for path in self._dir.iterdir():
            remove_file(path)
        self._cache.clear()
        self._events.clear()

    def close(self) -> None:
        """Clear all channels and remove the channels directory."""
        self.clear()
        if self._dir.exists():
            remove_empty_dirs(self._dir)
            if not self._dir.exists():
                logger.debug("Removed channels directory %s", self._dir)

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
