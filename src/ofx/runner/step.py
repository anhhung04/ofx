"""Step runner for executing workflow steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.models.job import Job
from ofx.models.step import RunType, Step
from ofx.runner.context import RunContext
from ofx.runner.error_helpers import coerce_timeout_minutes as _timeout_int
from ofx.runner.executors.step import StepExecutor
from ofx.runner.logging import bubble_context_log
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.run_defaults import model_field_is_explicitly_set
from ofx.runner.runner import Runner
from ofx.runner.step_mixin import StepRunnerMixin
from ofx.utils.tempfiles import make_temp_file

RUNNER_OUTPUTS_ENV = "RUNNER_OUTPUTS"
OFX_OUTPUTS_ENV = "OFX_OUTPUTS"


def prepare_outputs_file_env(
    envs: dict[str, Any],
    *,
    interactive: bool,
    include_ofx_alias: bool = False,
) -> Path | None:
    """Create or reuse the outputs file path injected into a command environment.

    Interactive steps get no file (``None`` is returned and no env var is
    set); otherwise an existing ``RUNNER_OUTPUTS`` value is reused or a fresh
    temp file is created and exposed as ``RUNNER_OUTPUTS`` (and, when
    requested, ``OFX_OUTPUTS``).
    """
    if interactive:
        return None

    existing = envs.get(RUNNER_OUTPUTS_ENV)
    if existing:
        outputs_file = Path(existing)
    else:
        outputs_file = make_temp_file(prefix=".tmp_out_")
    envs[RUNNER_OUTPUTS_ENV] = str(outputs_file)

    if include_ofx_alias:
        envs[OFX_OUTPUTS_ENV] = str(outputs_file)

    return outputs_file


class StepRunner(StepRunnerMixin, Runner[Step]):
    def __init__(
        self,
        step: Step,
        context: RunContext,
        parent: Runner[Job],
        executor: StepExecutor | None = None,
    ):
        step_executor = executor or StepExecutor()
        super().__init__(
            step,
            context,
            parent,
            parent.registry,
            executor=step_executor,
        )
        self._outputs_file: Path | None = None

    async def _pre_run(self) -> None:
        self._run_type = self.model.get_run_type()

        # Module steps capture step outputs through the RUNNER_OUTPUTS env
        # file; workflow and pipe steps do not.
        if self._run_type == RunType.MODULE:
            self._outputs_file = prepare_outputs_file_env(
                self.ctx.envs,
                interactive=self.model.interactive,
                include_ofx_alias=True,
            )

        await self._prepare_step_run(
            run_if_message="Step skipped due to run_if condition"
        )

        self.update_env(self.model.env)
        resolved_run_with = await self._resolve_template(self.model.run_with)
        if resolved_run_with:
            self.update_inputs(resolved_run_with)
        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"env", "secrets", "run_with"}),
        )

    def _produce_log(self, message: Any) -> str:
        return bubble_context_log(
            self.parent,
            message,
            step_index=getattr(self.model, "step_index", "?"),
        )

    def _resolve_working_dir(self) -> Path:
        base_path = Path(self.ctx.vars.get("working_directory", Path.cwd()))
        if not base_path.is_absolute():
            base_path = base_path.resolve()
        if not model_field_is_explicitly_set(self.model, "working_directory"):
            return base_path

        step_path = Path(self.model.working_directory)
        if step_path.is_absolute():
            return step_path
        return (base_path / step_path).resolve()

__all__ = ["StepRunner", "_timeout_int", "prepare_outputs_file_env"]
