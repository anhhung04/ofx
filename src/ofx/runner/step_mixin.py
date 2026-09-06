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
from ofx.runner.step_fields import BASE_STEP_TEMPLATE_FIELDS, RUN_TYPE_TEMPLATE_FIELDS

_MAX_BACKOFF_SECONDS = 300
_JITTER_MIN = 0.5
_JITTER_MAX = 1.0
_DEFAULT_TIMEOUT_MINUTES = 60

class StepRunnerMixin:
    """Mixin providing methods shared by StepRunner and CloudStepRunner."""

    async def _prepare_step_run(
        self,
        *,
        run_if_message: str,
        resolve_workflow_fields: bool = True,
    ) -> None:
        """Common step pre-run: retry defaults, run type, templates, timeout, run_if."""
        self._apply_retry_profile_defaults()
        self._run_type = self.model.get_run_type()
        fields = list(BASE_STEP_TEMPLATE_FIELDS)
        if resolve_workflow_fields or self._run_type is not RunType.WORKFLOW:
            fields.extend(RUN_TYPE_TEMPLATE_FIELDS[self._run_type])
        await self._resolve_template_fields(fields)
        await self._resolve_timeout_field()
        self._ensure_run_if_condition(run_if_message)

    def _ensure_run_if_condition(self, message: str) -> None:
        """Validate ``run_if`` for the current step or cancel it."""
        if self._evaluate_run_if(
            self.model.run_if,
            self._run_if_context(),
        ):
            return
        self._state_machine.transition(RunnerStatus.CANCELED)
        raise ConditionNotMetError(message)

    def _apply_retry_profile_defaults(self) -> None:
        """Apply profile retry/timeout settings to the step.

        Precedence (highest → lowest):
          1. **Profile** — profile-level knobs and ``retry_profiles`` are
             the governance layer; they override step values.
          2. **Step** — explicit YAML values apply when the profile does
             not specify a value for that field.
          3. **Default** — built-in Step model defaults.
        """
        profile = self.ctx.vars.get("profile_model")
        if profile is None:
            return

        policy_name = getattr(profile, "retry_policy", "standard") or "standard"
        profiles = getattr(profile, "retry_profiles", {}) or {}
        policy = profiles.get(policy_name)
        if not isinstance(policy, dict):
            policy = {}

        from ofx.profiles.models import OFXProfile

        def _resolve_profile_or_policy_int(
            profile_field: str,
            policy_field: str,
            *,
            ignore_zero_policy: bool = False,
        ) -> int | None:
            default_value = OFXProfile.model_fields[profile_field].default
            profile_value = getattr(profile, profile_field, None)
            if profile_value is not None and profile_value != default_value:
                return int(profile_value)

            if policy_field not in policy:
                return None

            policy_value = int(policy[policy_field])
            if ignore_zero_policy and policy_value == 0:
                return None
            return policy_value

        retry_override = _resolve_profile_or_policy_int(
            "max_retries",
            "retry",
            ignore_zero_policy=True,
        )
        if retry_override is not None:
            self.model.retry = retry_override

        retry_delay_policy_value = (
            int(policy["retry_delay"]) if "retry_delay" in policy else None
        )
        if retry_delay_policy_value is not None:
            self.model.retry_delay = retry_delay_policy_value

        timeout_override = _resolve_profile_or_policy_int(
            "timeout_minutes",
            "timeout",
        )
        if timeout_override is not None:
            self.model.timeout = timeout_override

    @staticmethod
    def _retry_delay_seconds(attempt: int, base_delay: int) -> float:
        """Compute exponential backoff with jitter capped to 5 minutes."""
        backoff = base_delay * (2**attempt)
        delay = min(backoff, _MAX_BACKOFF_SECONDS)
        return delay * uniform(_JITTER_MIN, _JITTER_MAX)

    async def _resolve_timeout_field(self) -> None:
        """Resolve a Jinja2 expression in ``self.model.timeout``."""
        timeout = self.model.timeout
        if not isinstance(timeout, str):
            return

        resolved = await self._resolve_template(timeout)
        try:
            self.model.timeout = int(float(resolved))
        except (ValueError, TypeError):
            self._log_warning(
                f"Invalid timeout expression result: {resolved!r}, using 60 min"
            )
            self.model.timeout = _DEFAULT_TIMEOUT_MINUTES

    def _save_runner_output(
        self,
        stdout: str,
        outputs: dict[str, Any] | None = None,
        *,
        missing_output_path_message: str | None = None,
        warn_on_missing_output_path: bool = False,
    ) -> None:
        """Persist runner output using the shared step-output helper."""
        output_path = self.ctx.output_path
        if not output_path:
            if missing_output_path_message and warn_on_missing_output_path:
                self._log_warning(missing_output_path_message)
            return

        job_id = self.parent.model.jid if self.parent else None
        if not job_id:
            return

        from ofx.runner.step_output import save_output_file

        save_output_file(
            output_path,
            job_id,
            self.model,
            stdout,
            outputs,
            log_fn=self._log_info,
        )

    def _format_typed_outputs(self, result) -> bool:
        """Show formatted typed-output tables if available.

        Returns ``True`` if typed outputs were displayed, ``False`` otherwise
        (caller should fall back to plain stdout logging).
        """
        outputs = getattr(result, "outputs", None)
        typed_outputs = outputs.get("typed_outputs") if isinstance(outputs, dict) else None
        typed_outputs = typed_outputs if isinstance(typed_outputs, list) else []
        if not typed_outputs:
            return False

        from ofx.runner.output_formatter import format_typed_outputs
        from ofx.settings import get_console

        format_typed_outputs(
            typed_outputs,
            task_name=self.model.name or self.model.task or "",
            console=get_console(),
        )
        return True

    def _emit_result_outputs(self, result) -> None:
        """Display stdout/stderr streams and optionally persist stdout."""
        from ofx.runner.step_output import log_output

        stdout = result.outputs.get("stdout", "")
        stderr = result.outputs.get("stderr", "")

        if not self._format_typed_outputs(result):
            log_output(self._log_info, "stdout", stdout)

        log_output(self._log_info, "stderr", stderr)

        if self.model.log_stdout and stdout and self.ctx.output_path:
            self._save_runner_output(
                stdout,
                result.outputs,
                missing_output_path_message="No output_path configured, skipping log file save.",
                warn_on_missing_output_path=True,
            )

    def _run_if_context(self) -> dict[str, Any]:
        """Build run_if evaluation context.

        Provides ``success()``, ``failure()``, ``canceled()``, and ``always()``
        helpers that inspect the previous step's status.
        """
        from ofx.runner.execution_results import build_run_if_context

        if not self.parent:
            return build_run_if_context([])

        step_index = self.model.step_index
        if step_index <= 0:
            return build_run_if_context([])

        previous_runner = getattr(self.parent, "_runners", {}).get(
            str(step_index - 1)
        )
        return build_run_if_context([previous_runner] if previous_runner is not None else [])

    def _build_timeline_params(self, result) -> dict[str, str]:
        """Build common timeline parameters from the step's run type.

        Returns a dict with ``command``, ``tool``, and ``target`` keys.
        """
        from ofx.runner.step_descriptors import step_timeline_params

        return step_timeline_params(self.model, outputs=result.outputs)
