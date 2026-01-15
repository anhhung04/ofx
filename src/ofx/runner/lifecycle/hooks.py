"""Hook management for step lifecycle events"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ofx.runner.core.models import RunContext, RunnerStatus
from ofx.settings import settings

if TYPE_CHECKING:
    from ofx.runner.core.base import BaseRunner

logger = logging.getLogger(settings.app_branding)


class HookManager:
    """Manages lifecycle hooks for steps (before_step, after_step, on_retry, on_skip, on_timeout)"""

    def __init__(self, parent_runner: "BaseRunner"):
        self._parent = parent_runner

    async def run_hook(
        self,
        hook_name: str,
        hooks: dict[str, str],
        shell: str | None,
        working_dir: Path,
        ctx: RunContext,
    ) -> None:
        """Execute a lifecycle hook if defined

        Args:
            hook_name: Name of the hook (e.g., 'before_step', 'after_step')
            hooks: Dictionary of hook name to script mappings
            shell: Shell to use for execution
            working_dir: Working directory for hook execution
            ctx: Execution context
        """
        if hook_name not in hooks:
            return

        hook_code = hooks[hook_name]
        logger.info(self._produce_log(f"Running '{hook_name}' hook..."))

        try:
            # Import here to avoid circular dependency
            from ofx.runner.executors.command import ScriptRunner

            hook_runner = ScriptRunner(
                hook_code,
                ctx.model_copy(),
                shell=shell,
                working_dir=working_dir,
                parent=self._parent,
                timeout_minutes=1,
            )
            result = await hook_runner.run()

            if result.status != RunnerStatus.COMPLETED:
                logger.warning(
                    self._produce_log(
                        f"'{hook_name}' hook failed with status {result.status}: {result.error}"
                    )
                )
        except Exception as e:
            logger.error(self._produce_log(f"Error executing '{hook_name}' hook: {e}"))

    def _produce_log(self, message: str) -> str:
        """Produce a log message through parent runner"""
        if self._parent and hasattr(self._parent, "_produce_log"):
            return self._parent._produce_log(f"[HookManager] {message}")
        return f"[HookManager] {message}"
