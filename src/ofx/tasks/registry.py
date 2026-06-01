"""Task registry — discover, register, and instantiate tool wrappers.

Uses the same decorator-based pattern as ``RunnerRegistry`` and
``CloudProviderRegistry`` elsewhere in OFX.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import threading
from collections.abc import Callable
from typing import Any

from ofx.tasks.base import Task

logger = logging.getLogger(__name__)

TASK_TOOLS_PACKAGE = "ofx.tasks.tools"


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
        return cls._task_class_or_error(name)(**kwargs)

    @classmethod
    def list_tasks(cls) -> list[str]:
        """Return sorted list of all registered task names."""
        cls._ensure_loaded()
        return sorted(cls._tasks.keys())

    @classmethod
    def get_by_category(cls, category: str) -> list[tuple[str, type[Task]]]:
        """Return tasks whose category starts with *category*."""
        cls._ensure_loaded()
        return cls._category_tasks(category)

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
            package = cls._task_tools_package()
            if package is None:
                return

            cls._import_task_modules(package.__path__)
            cls._loaded = True

    @classmethod
    def _task_class_or_error(cls, name: str) -> type[Task]:
        task_cls = cls.get(name)
        if task_cls is not None:
            return task_cls

        available = ", ".join(sorted(cls._tasks)) or "(none)"
        raise KeyError(f"Task '{name}' is not registered. Available: {available}")

    @classmethod
    def _category_tasks(cls, category: str) -> list[tuple[str, type[Task]]]:
        return [
            (name, task_cls)
            for name, task_cls in sorted(cls._tasks.items())
            if task_cls.category.startswith(category)
        ]

    @classmethod
    def _task_tools_package(cls) -> Any | None:
        try:
            return importlib.import_module(TASK_TOOLS_PACKAGE)
        except ImportError as exc:
            logger.debug("Failed to import task tools package: %s", exc)
            return None

    @classmethod
    def _import_task_modules(cls, package_paths: Any) -> None:
        for module_name in cls._task_module_names(package_paths):
            try:
                importlib.import_module(module_name)
            except ImportError as exc:
                logger.debug(
                    "Skipping task module %s: %s",
                    module_name.removeprefix(f"{TASK_TOOLS_PACKAGE}."),
                    exc,
                )

    @classmethod
    def _task_module_names(cls, package_paths: Any) -> list[str]:
        return [
            f"{TASK_TOOLS_PACKAGE}.{info.name}"
            for info in pkgutil.iter_modules(package_paths)
        ]

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._tasks.pop(name, None)

    @classmethod
    def clear(cls) -> None:
        cls._tasks.clear()
        cls._loaded = False
