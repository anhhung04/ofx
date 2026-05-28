"""Executor for job-level runner orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

from ofx.models.config import DefaultConfig
from ofx.runner.context import ConditionNotMetError, RunnerContextBuilder, RunnerStatus
from ofx.runner.executors.base import Executor
from ofx.runner.registry_keys import RunnerRegistryKeys


class JobExecutor(Executor):
    async def _prepare_job_context(self, runner) -> None:
        await runner._resolve_template_fields(
            ["name", "needs", "run_if", "env", "defaults"]
        )
        runner.ctx = RunnerContextBuilder(runner.ctx).with_env(runner.model.env)
        runner._log_debug(f"Resolved job: {runner.model.model_dump(exclude={'steps'})}")

    async def _store_job_model(self, runner) -> None:
        await runner.reg_set(
            RunnerRegistryKeys.MODEL,
            runner.model.model_dump(exclude={"steps", "env"}),
        )

    async def pre_run(self, runner) -> None:
        await self._prepare_job_context(runner)

        self.check_dependencies_and_run_if(runner)

        job_default_config = runner.model.defaults.model_dump(exclude_defaults=True)
        workflow_default_config = runner.parent.model.defaults.model_dump()  # type: ignore[union-attr]
        for key, value in job_default_config.items():
            workflow_default_config[key] = value
        runner.model.defaults = DefaultConfig.model_validate(workflow_default_config)

        await self._store_job_model(runner)

    async def do_run(self, runner) -> None:
        runner._log_info(f"Starting job '{runner.model.name or runner.model.jid}'")
        await self.run_steps(runner)

    async def post_run(self, runner) -> None:
        await self.save_job_results(runner)
        await self.cleanup_temp_task_files(runner)

    async def run_steps(self, runner) -> None:
        for step in runner.model.steps:
            step_ctx = runner._child_context(
                update={
                    "secrets": runner.ctx.secrets if step.secrets != "inherit" else {},
                },
            )

            from ofx.runner.step import StepRunner

            step_runner = StepRunner(step, step_ctx, runner)
            step_runner.log_level = logging.CRITICAL
            runner._runners[str(step.step_index)] = step_runner
            result = await step_runner.run()
            if step_runner.is_failed and not step.continue_on_error:
                raise RuntimeError(
                    self._job_step_failed(step.name or step.step_index, result.error)
                )

    def check_dependencies_and_run_if(self, runner) -> None:
        if isinstance(runner.model.needs, str):
            runner.model.needs = [runner.model.needs]

        dep_runners = []
        for job_id in runner.model.needs:
            dep_runner = runner.parent.runners.get(job_id)
            if not dep_runner:
                raise RuntimeError(
                    f"Job dependency '{job_id}' is missing from workflow runners."
                )
            dep_runners.append(dep_runner)

        run_if_expr = runner.model.run_if
        if run_if_expr is True and dep_runners:
            run_if_expr = "success()"

        from ofx.runner.execution_results import build_run_if_context

        if not runner._evaluate_run_if(
            run_if_expr,
            build_run_if_context(dep_runners),
        ):
            runner._state_machine.transition(RunnerStatus.CANCELED)
            raise ConditionNotMetError(runner._produce_log("Job condition is not met"))

    async def save_job_results(self, runner) -> None:
        resolved_outputs = await runner._resolve_job_outputs()
        if resolved_outputs:
            await runner.reg_update(RunnerRegistryKeys.OUTPUTS, resolved_outputs)

        from ofx.runner.execution_results import build_job_execution_result

        job_exec = build_job_execution_result(runner, runner._runners)
        await runner.reg_set(RunnerRegistryKeys.EXECUTION, job_exec.to_dict())

    async def cleanup_temp_task_files(self, runner) -> None:
        for step_runner in runner._runners.values():
            try:
                result = await step_runner.get_result()
            except Exception as exc:
                runner._log_debug(
                    f"Job '{runner.model.jid}': failed to read step result for "
                    f"temp task cleanup: {exc}"
                )
                continue

            self._cleanup_temp_task_output(runner, result.outputs.get("output_file", ""))

    def _cleanup_temp_task_output(self, runner, output_file: str) -> None:
        if not output_file or ".ofx_task_" not in output_file:
            return

        try:
            Path(output_file).unlink(missing_ok=True)
        except OSError as exc:
            runner._log_debug(
                f"Job '{runner.model.jid}': failed to remove temp task file "
                f"'{output_file}': {exc}"
            )
        except ValueError as exc:
            runner._log_debug(
                f"Job '{runner.model.jid}': invalid temp task output path "
                f"'{output_file}': {exc}"
                )

    def _job_step_failed(self, step_name, error) -> str:
        from ofx.runner.error_helpers import job_step_failed

        return job_step_failed(step_name, error)
