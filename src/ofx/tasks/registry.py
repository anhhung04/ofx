"""Task registry — discover, register, and instantiate tool wrappers.

Uses the same decorator-based pattern as ``RunnerRegistry`` and
``CloudProviderRegistry`` elsewhere in OFX.
"""

from __future__ import annotations

import importlib
import pkgutil
import threading
from collections.abc import Callable
from typing import Any

from ofx.tasks.base import Task


class TaskRegistry:
    """Central registry of available task wrappers."""

    _tasks: dict[str, type[Task]] = {}
    _lock = threading.Lock()

    # ── Registration ───────────────────────────────────────────────

    @classmethod
    def register(cls, name: str) -> Callable[[type[Task]], type[Task]]:
        """Decorator to register a task class under *name*.

        Usage::

            @TaskRegistry.register("nmap")
            class NmapTask(Task):
                ...
        """

        def decorator(task_cls: type[Task]) -> type[Task]:
            if name in cls._tasks:
                raise ValueError(
                    f"Task '{name}' is already registered by {cls._tasks[name].__name__}"
                )
            cls._tasks[name] = task_cls
            return task_cls

        return decorator

    # ── Lookup ─────────────────────────────────────────────────────

    @classmethod
    def get(cls, name: str) -> type[Task] | None:
        """Return the task class for *name*, or ``None``."""
        cls._ensure_loaded()
        return cls._tasks.get(name)

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> Task:
        """Instantiate a registered task by name."""
        task_cls = cls.get(name)
        if task_cls is None:
            available = ", ".join(sorted(cls._tasks)) or "(none)"
            raise KeyError(f"Task '{name}' is not registered. Available: {available}")
        return task_cls(**kwargs)

    @classmethod
    def list_tasks(cls) -> list[str]:
        """Return sorted list of all registered task names."""
        cls._ensure_loaded()
        return sorted(cls._tasks.keys())

    @classmethod
    def get_by_category(cls, category: str) -> list[tuple[str, type[Task]]]:
        """Return tasks whose category starts with *category*."""
        cls._ensure_loaded()
        return [
            (name, t)
            for name, t in sorted(cls._tasks.items())
            if t.category.startswith(category)
        ]

    # ── Internals ──────────────────────────────────────────────────

    _loaded = False

    @classmethod
    def _ensure_loaded(cls) -> None:
        """Auto-import all modules under ``ofx.tasks.tools`` once.

        Uses double-checked locking to avoid duplicate imports under
        concurrent access.
        """
        if cls._loaded:
            return
        with cls._lock:
            if cls._loaded:
                return
            cls._loaded = True
            try:
                import ofx.tasks.tools as _pkg

                for info in pkgutil.iter_modules(_pkg.__path__):
                    importlib.import_module(f"ofx.tasks.tools.{info.name}")
            except ImportError:
                pass

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._tasks.pop(name, None)

    @classmethod
    def clear(cls) -> None:
        cls._tasks.clear()
        cls._loaded = False
