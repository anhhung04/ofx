"""Executor for job-level runner orchestration."""

from __future__ import annotations

import logging
from typing import Any

from ofx.models.config import DefaultConfig
from ofx.runner.context import ConditionNotMetError, RunnerStatus, context_copy, context_with_update
from ofx.runner.executors.base import Executor
from ofx.utils.file_cleanup import remove_file
from ofx.runner.registry_keys import RunnerRegistryKeys

class JobExecutor(Executor):
    async def pre_run(self, runner) -> None:
        await self._prepare_job_context(runner)
        self.check_dependencies_and_run_if(runner)
        await self._store_job_model(runner)

    async def _prepare_job_context(self, runner) -> None:
        def _merge_overrides(base: dict, overrides: dict) -> None:
            for key, value in overrides.items():
                if isinstance(base.get(key), dict) and isinstance(value, dict):
                    _merge_overrides(base[key], value)
                else:
                    base[key] = value

        await runner._resolve_template_fields(
            ["name", "needs", "run_if", "env", "defaults"]
        )
        runner.update_env(runner.model.env)
        runner._log_debug(f"Resolved job: {runner.model.model_dump(exclude={'steps'})}")

        workflow_defaults = runner.parent.model.defaults.model_dump()
        _merge_overrides(
            workflow_defaults,
            runner.model.defaults.model_dump(exclude_defaults=True),
        )
        runner.model.defaults = DefaultConfig.model_validate(workflow_defaults)

    async def _store_job_model(self, runner) -> None:
        await runner.reg_set(
            RunnerRegistryKeys.MODEL,
            runner.model.model_dump(exclude={"steps", "env"}),
        )

    async def do_run(self, runner) -> None:
        runner._log_info(f"Starting job '{runner.model.name or runner.model.jid}'")
        await self._execute_steps(runner)

    async def post_run(self, runner) -> None:
        await self.save_job_results(runner)
        await self.cleanup_temp_task_files(runner)

    async def _execute_steps(
        self,
        runner,
        *,
        suffix: str = "",
        loop_ctx=None,
    ) -> None:
        for step in runner.model.steps:
            step_ctx = context_copy(loop_ctx or runner.ctx)
            if getattr(step, "secrets", None) != "inherit":
                step_ctx = context_with_update(step_ctx, {"secrets": {}})
            step_runner = self._create_step_runner(
                runner,
                step,
                step_ctx,
            )
            step_runner.log_level = logging.CRITICAL
            runner._runners[f"{step.step_index}{suffix}"] = step_runner
            result = await step_runner.run()
            if step_runner.is_failed and not step.continue_on_error:
                from ofx.runner.error_helpers import job_step_failed

                raise RuntimeError(
                    job_step_failed(step.name or step.step_index, result.error)
                )

    def _create_step_runner(self, runner, step, step_ctx):
        from ofx.runner.step import StepRunner

        return StepRunner(step, step_ctx, runner)

    def check_dependencies_and_run_if(self, runner) -> None:
        from ofx.runner.execution_results import build_run_if_context

        needs = [runner.model.needs] if isinstance(runner.model.needs, str) else list(runner.model.needs)
        dep_runners: list[Any] = []
        for job_id in needs:
            dep_runner = runner.parent.runners.get(job_id)
            if not dep_runner:
                raise RuntimeError(
                    f"Job dependency '{job_id}' is missing from workflow runners."
                )
            dep_runners.append(dep_runner)

        runner.model.needs = needs
        run_if_expr = "success()" if runner.model.run_if is True and dep_runners else runner.model.run_if
        if runner._evaluate_run_if(run_if_expr, build_run_if_context(dep_runners)):
            return
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
            output_file = result.outputs.get("output_file", "")
            exc = remove_file(output_file, required_substring=".ofx_task_")
            if exc is None:
                continue
            if isinstance(exc, ValueError):
                runner._log_debug(
                    f"Job '{runner.model.jid}': invalid temp task output path "
                    f"'{output_file}': {exc}"
                )
                continue
            runner._log_debug(
                f"Job '{runner.model.jid}': failed to remove temp task file "
                f"'{output_file}': {exc}"
            )
