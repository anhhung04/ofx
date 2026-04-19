"""Shared helpers for StepRunner and CloudStepRunner.

Extracted to eliminate code duplication between local and cloud step
execution paths while keeping each class focused on its own execution
model.
"""

from __future__ import annotations

from random import uniform
from typing import Any

from ofx.runner.core import RunnerStatus

# Retry backoff constants
_MAX_BACKOFF_SECONDS = 300  # 5 minutes
_JITTER_MIN = 0.5
_JITTER_MAX = 1.0
_DEFAULT_TIMEOUT_MINUTES = 60


class StepRunnerMixin:
    """Mixin providing methods shared by StepRunner and CloudStepRunner."""

    # ------------------------------------------------------------------
    # Retry / profile helpers
    # ------------------------------------------------------------------

    def _apply_retry_profile_defaults(self) -> None:
        """Apply retry policy defaults only when step fields are not explicit."""
        profile = self.ctx.vars.get("profile_model")  # type: ignore[attr-defined]
        if profile is None:
            return

        policy_name = getattr(profile, "retry_policy", "standard") or "standard"
        profiles = getattr(profile, "retry_profiles", {}) or {}
        policy = profiles.get(policy_name)
        if not isinstance(policy, dict):
            return

        explicitly_set = set(getattr(self.model, "model_fields_set", set()))  # type: ignore[attr-defined]

        if "retry" not in explicitly_set and "retry" in policy:
            self.model.retry = int(policy["retry"])  # type: ignore[attr-defined]
        if "retry_delay" not in explicitly_set and "retry_delay" in policy:
            self.model.retry_delay = int(policy["retry_delay"])  # type: ignore[attr-defined]
        if "timeout" not in explicitly_set and "timeout" in policy:
            self.model.timeout = int(policy["timeout"])  # type: ignore[attr-defined]

    @staticmethod
    def _retry_delay_seconds(attempt: int, base_delay: int) -> float:
        """Compute exponential backoff with jitter capped to 5 minutes."""
        backoff = base_delay * (2**attempt)
        delay = min(backoff, _MAX_BACKOFF_SECONDS)
        return delay * uniform(_JITTER_MIN, _JITTER_MAX)

    # ------------------------------------------------------------------
    # Template / timeout resolution
    # ------------------------------------------------------------------

    async def _resolve_timeout_field(self) -> None:
        """Resolve a Jinja2 expression in ``self.model.timeout``."""
        if isinstance(self.model.timeout, str):  # type: ignore[attr-defined]
            resolved = await self._resolve_template(self.model.timeout)  # type: ignore[attr-defined]
            try:
                self.model.timeout = int(float(resolved))  # type: ignore[attr-defined]
            except (ValueError, TypeError):
                self._log_warning(  # type: ignore[attr-defined]
                    f"Invalid timeout expression result: {resolved!r}, using 60 min"
                )
                self.model.timeout = _DEFAULT_TIMEOUT_MINUTES  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _log_output(self, stream: str, content: str) -> None:
        """Log a stdout/stderr stream to the console, truncating long output."""
        from ofx.runner.core.step_output import log_output

        log_output(self._log_info, stream, content)  # type: ignore[attr-defined]

    def _format_typed_outputs(self, result) -> bool:
        """Show formatted typed-output tables if available.

        Returns ``True`` if typed outputs were displayed, ``False`` otherwise
        (caller should fall back to plain stdout logging).
        """
        typed_outputs = result.outputs.get("typed_outputs")
        if typed_outputs and isinstance(typed_outputs, list) and len(typed_outputs) > 0:
            from ofx.runner.execution.output_formatter import format_typed_outputs
            from ofx.settings import get_console

            format_typed_outputs(
                typed_outputs,
                task_name=self.model.name or self.model.task or "",  # type: ignore[attr-defined]
                console=get_console(),
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Conditional execution
    # ------------------------------------------------------------------

    def _run_if_context(self) -> dict[str, Any]:
        """Build run_if evaluation context.

        Provides ``success()``, ``failure()``, ``canceled()``, and ``always()``
        helpers that inspect the previous step's status.
        """
        prev_runner = None
        if self.parent and self.model.step_index > 0:  # type: ignore[attr-defined]
            prev_key = str(self.model.step_index - 1)  # type: ignore[attr-defined]
            prev_runner = getattr(self.parent, "_runners", {}).get(prev_key)  # type: ignore[attr-defined]

        if prev_runner is None:
            return {
                "success": lambda: True,
                "failure": lambda: False,
                "canceled": lambda: False,
                "always": lambda: True,
            }

        return {
            "success": lambda: prev_runner.is_success,
            "failure": lambda: prev_runner.is_failed,
            "canceled": lambda: prev_runner.status == RunnerStatus.CANCELED,
            "always": lambda: True,
        }

    # ------------------------------------------------------------------
    # Timeline helpers
    # ------------------------------------------------------------------

    def _build_timeline_params(self, result) -> dict[str, str]:
        """Build common timeline parameters from the step's run type.

        Returns a dict with ``command``, ``tool``, and ``target`` keys.
        """
        from ofx.models.step import RunType

        command = ""
        tool = ""
        target = ""
        rt = self._run_type or self.model.get_run_type()  # type: ignore[attr-defined]

        if rt == RunType.COMMAND:
            command = self.model.run or ""  # type: ignore[attr-defined]
        elif rt == RunType.TASK:
            task_name = self.model.task or ""  # type: ignore[attr-defined]
            tool = task_name
            target = str(
                self.model.run_with.get(  # type: ignore[attr-defined]
                    "target", self.model.run_with.get("targets", "")  # type: ignore[attr-defined]
                )
            )
            command = result.outputs.get("command", f"task:{task_name}")
        elif rt == RunType.SCRIPT:
            command = f"script:{self.model.name or 'inline'}"  # type: ignore[attr-defined]
        elif rt == RunType.SCRIPT_FILE:
            command = f"script_file:{self.model.script_file or ''}"  # type: ignore[attr-defined]
        elif rt == RunType.WORKFLOW:
            command = f"uses:{self.model.uses or ''}"  # type: ignore[attr-defined]

        return {"command": command, "tool": tool, "target": target}
