"""Executor for workflow step runners."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ofx.models.step import RunType
from ofx.runner.context import RunnerStatus, RunResult, normalized_runner_status_value
from ofx.runner.error_helpers import (
    coerce_timeout_minutes,
    step_execution_error,
    step_retry_error,
    step_timeout_error,
)
from ofx.runner.execution_results import build_step_execution_result_for_runner
from ofx.runner.executors.base import Executor
from ofx.utils.file_cleanup import remove_file
from ofx.runner.handlers import registry as default_handler_registry
from ofx.runner.registry_keys import RunnerRegistryKeys

if TYPE_CHECKING:
    from ofx.runner.runner import Runner

class StepExecutor(Executor):
    @staticmethod
    async def _store_child_result(runner, result: RunResult) -> None:
        runner._error = result.error
        await runner.reg_set(RunnerRegistryKeys.OUTPUTS, result.outputs)
        await runner.reg_set(
            RunnerRegistryKeys.RESULT,
            result.model_dump(exclude={"outputs"}),
        )

    async def do_run(self, runner) -> None:
        max_attempts = runner.model.retry + 1
        timeout_seconds = coerce_timeout_minutes(runner.model.timeout) * 60

        last_res = None
        attempt_errors: list[str] = []

        for attempt in range(max_attempts):
            try:
                runner_factory = getattr(runner, "_create_runner", None)
                if runner_factory is not None:
                    child_runner = runner_factory()
                else:
                    registry = getattr(runner, "_handler_registry", default_handler_registry)
                    if (
                        runner.model.interactive
                        and runner.ctx.allow_interactive
                        and runner._run_type == RunType.WORKFLOW
                    ):
                        runner._log_warning(
                            "Interactive mode is not supported for workflow steps ('uses'). "
                            "Ignoring interactive flag."
                        )
                    child_runner = registry.get(runner._run_type)(runner)
                res = await asyncio.wait_for(child_runner.run(), timeout=timeout_seconds)
                last_res = res

                if child_runner.is_success:
                    await self._store_child_result(runner, res)
                    runner._log_debug(f"result: {await runner.get_result()}")
                    return

                raise RuntimeError(step_execution_error(res.status, res.error))
            except TimeoutError as exc:
                raise RuntimeError(
                    step_timeout_error(coerce_timeout_minutes(runner.model.timeout))
                ) from exc
            except Exception as exc:
                err_msg = str(exc)
                attempt_errors.append(f"attempt {attempt + 1}: {err_msg}")
                if attempt < max_attempts - 1:
                    next_delay = runner._retry_delay_seconds(
                        attempt=attempt,
                        base_delay=runner.model.retry_delay,
                    )
                    runner._log_info(
                        f"Retry {attempt + 2}/{max_attempts} in {next_delay:.1f}s - {err_msg}"
                    )
                    await asyncio.sleep(next_delay)
                    continue

                attempts_suffix = f"\n  Attempts: {'; '.join(attempt_errors)}"
                if last_res:
                    await self._store_child_result(runner, last_res)
                    if last_res.status != RunnerStatus.COMPLETED:
                        raise RuntimeError(
                            step_retry_error(max_attempts, last_res.error)
                            + attempts_suffix
                        ) from exc

                raise RuntimeError(
                    step_retry_error(max_attempts, exc)
                    + attempts_suffix
                ) from exc

    async def post_run(self, runner) -> None:
        result = await runner.get_result()
        runner._emit_result_outputs(result)

        await self._store_step_execution(
            runner,
            status=normalized_runner_status_value(result.status),
            error=result.error,
            outputs=result.outputs,
        )

        if runner._outputs_file:
            remove_file(runner._outputs_file)

        if runner.model.log_command:
            from ofx.runner.timeline import log_step

            params = runner._build_timeline_params(result)
            log_step(
                ctx_vars=runner.ctx.vars,
                step_name=runner.model.name or f"step{runner.model.step_index}",
                status=normalized_runner_status_value(result.status),
                duration_ms=runner.duration_ms(),
                exit_code=result.outputs.get("exit_code"),
                **params,
            )

    async def on_failure(self, runner) -> None:
        try:
            result = await runner.get_result()
            await self._store_step_execution(
                runner,
                status=RunnerStatus.FAILED.value,
                error=result.error or runner._error,
                outputs=result.outputs,
            )
        except Exception as exc:
            runner._log_debug(f"Failed to save step execution on failure: {exc}")
        if runner._outputs_file:
            remove_file(runner._outputs_file)

    async def _store_step_execution(
        self,
        runner,
        *,
        status: str,
        error: str | None,
        outputs: dict,
    ) -> None:
        execution = build_step_execution_result_for_runner(
            runner,
            status=status,
            error=error,
            outputs=outputs,
        )
        await runner.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())
