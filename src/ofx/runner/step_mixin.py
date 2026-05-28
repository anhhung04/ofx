"""Shared helpers for StepRunner and CloudStepRunner.

Extracted to eliminate code duplication between local and cloud step
execution paths while keeping each class focused on its own execution
model.
"""

from __future__ import annotations

from random import uniform
from typing import Any

from ofx.models.step import RunType
from ofx.runner.context import ConditionNotMetError, RunnerStatus

# Retry backoff constants
_MAX_BACKOFF_SECONDS = 300  # 5 minutes
_JITTER_MIN = 0.5
_JITTER_MAX = 1.0
_DEFAULT_TIMEOUT_MINUTES = 60
_COMMON_TEMPLATE_FIELDS = (
    "name",
    "shell",
    "working_directory",
    "log_stdout",
    "log_command",
    "env",
    "run_if",
)
_RUN_TYPE_TEMPLATE_FIELDS = {
    RunType.WORKFLOW: ("uses",),
    RunType.SCRIPT: ("script",),
    RunType.COMMAND: ("run",),
    RunType.SCRIPT_FILE: ("script_file",),
    RunType.TASK: ("task", "run_with"),
    RunType.PIPE: (),
}


class StepRunnerMixin:
    """Mixin providing methods shared by StepRunner and CloudStepRunner."""

    def _prepare_step_run_type(self):
        """Apply retry defaults and cache the current step run type."""
        self._apply_retry_profile_defaults()  # type: ignore[attr-defined]
        self._run_type = self.model.get_run_type()  # type: ignore[attr-defined]
        return self._run_type

    async def _resolve_step_pre_run_fields(
        self,
        *,
        resolve_workflow: bool = True,
    ) -> None:
        """Resolve template-backed fields and timeout for the current step."""
        await self._resolve_template_fields(  # type: ignore[attr-defined]
            self._template_fields_for_run_type(  # type: ignore[attr-defined]
                self._run_type,  # type: ignore[attr-defined]
                resolve_workflow=resolve_workflow,
            )
        )
        await self._resolve_timeout_field()  # type: ignore[attr-defined]

    def _cancel_step_for_unmet_condition(self, message: str) -> None:
        """Cancel the current step when its run_if condition evaluates false."""
        self._state_machine.transition(RunnerStatus.CANCELED)  # type: ignore[attr-defined]
        raise ConditionNotMetError(message)

    @staticmethod
    def _template_fields_for_run_type(
        run_type: RunType,
        *,
        resolve_workflow: bool = True,
    ) -> list[str]:
        fields = list(_COMMON_TEMPLATE_FIELDS)
        if run_type is RunType.WORKFLOW and not resolve_workflow:
            return fields
        fields.extend(_RUN_TYPE_TEMPLATE_FIELDS[run_type])
        return fields

    # ------------------------------------------------------------------
    # Retry / profile helpers
    # ------------------------------------------------------------------

    def _apply_retry_profile_defaults(self) -> None:
        """Apply profile retry/timeout settings to the step.

        Precedence (highest → lowest):
          1. **Profile** — profile-level knobs and ``retry_profiles`` are
             the governance layer; they override step values.
          2. **Step** — explicit YAML values apply when the profile does
             not specify a value for that field.
          3. **Default** — built-in Step model defaults.
        """
        profile = self.ctx.vars.get("profile_model")  # type: ignore[attr-defined]
        if profile is None:
            return

        policy_name = getattr(profile, "retry_policy", "standard") or "standard"
        profiles = getattr(profile, "retry_profiles", {}) or {}
        policy = profiles.get(policy_name)
        if not isinstance(policy, dict):
            policy = {}

        # ── retry ──────────────────────────────────────────────────
        # Top-level max_retries wins; fall back to policy; then step.
        from ofx.profiles.models import OFXProfile

        max_retries = getattr(profile, "max_retries", None)
        default_max_retries = OFXProfile.model_fields["max_retries"].default
        if max_retries is not None and max_retries != default_max_retries:
            self.model.retry = int(max_retries)  # type: ignore[attr-defined]
        elif "retry" in policy:
            policy_retry = int(policy["retry"])
            if policy_retry != 0:
                self.model.retry = policy_retry  # type: ignore[attr-defined]

        # ── retry_delay ────────────────────────────────────────────
        if "retry_delay" in policy:
            self.model.retry_delay = int(policy["retry_delay"])  # type: ignore[attr-defined]

        # ── timeout ────────────────────────────────────────────────
        # Top-level timeout_minutes wins; fall back to policy; then step.
        timeout_minutes = getattr(profile, "timeout_minutes", None)
        default_timeout = OFXProfile.model_fields["timeout_minutes"].default
        if timeout_minutes is not None and timeout_minutes != default_timeout:
            self.model.timeout = int(timeout_minutes)  # type: ignore[attr-defined]
        elif "timeout" in policy:
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
        from ofx.runner.step_output import log_output

        log_output(self._log_info, stream, content)  # type: ignore[attr-defined]

    def _save_runner_output(
        self,
        stdout: str,
        outputs: dict[str, Any] | None = None,
        *,
        missing_output_path_message: str | None = None,
        warn_on_missing_output_path: bool = False,
    ) -> None:
        """Persist runner output using the shared step-output helper."""
        from ofx.runner.step_output import save_runner_output_file

        save_runner_output_file(
            self.ctx.output_path,  # type: ignore[attr-defined]
            self.parent.model.jid if self.parent else None,  # type: ignore[attr-defined]
            self.model,  # type: ignore[attr-defined]
            stdout,
            outputs,
            log_fn=self._log_info,  # type: ignore[attr-defined]
            missing_output_path_message=missing_output_path_message,
            warn_fn=self._log_warning if warn_on_missing_output_path else None,  # type: ignore[attr-defined]
        )

    def _format_typed_outputs(self, result) -> bool:
        """Show formatted typed-output tables if available.

        Returns ``True`` if typed outputs were displayed, ``False`` otherwise
        (caller should fall back to plain stdout logging).
        """
        typed_outputs = result.outputs.get("typed_outputs")
        if typed_outputs and isinstance(typed_outputs, list) and len(typed_outputs) > 0:
            from ofx.runner.output_formatter import format_typed_outputs
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
        from ofx.runner.step_descriptors import step_timeline_params

        return step_timeline_params(self.model, outputs=result.outputs)  # type: ignore[attr-defined]
