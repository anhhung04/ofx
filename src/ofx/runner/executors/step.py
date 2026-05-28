"""Executor for workflow step runners."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

from ofx.runner.context import RunnerStatus, RunResult
from ofx.runner.error_helpers import (
    coerce_timeout_minutes,
    step_execution_error,
    step_retry_error,
    step_timeout_error,
)
from ofx.runner.execution_results import build_step_execution_result
from ofx.runner.executors.base import Executor
from ofx.runner.handlers import registry as default_handler_registry
from ofx.runner.registry_keys import RunnerRegistryKeys

if TYPE_CHECKING:
    from ofx.runner.runner import BaseRunner


class StepExecutor(Executor):
    async def do_run(self, runner) -> None:
        max_attempts = runner.model.retry + 1
        timeout_seconds = coerce_timeout_minutes(runner.model.timeout) * 60

        last_res = None
        attempt_errors: list[str] = []

        for attempt in range(max_attempts):
            try:
                child_runner = self.create_runner(runner)
                res = await asyncio.wait_for(child_runner.run(), timeout=timeout_seconds)
                last_res = res

                if child_runner.is_success:
                    await self._apply_run_result(runner, res)
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
                else:
                    if last_res:
                        await self._apply_run_result(runner, last_res)
                        if last_res.status != RunnerStatus.COMPLETED:
                            raise RuntimeError(
                                step_retry_error(max_attempts, last_res.error)
                                + f"\n  Attempts: {'; '.join(attempt_errors)}"
                            ) from exc
                    else:
                        raise RuntimeError(
                            step_retry_error(max_attempts, exc)
                            + f"\n  Attempts: {'; '.join(attempt_errors)}"
                        ) from exc

        runner._log_debug(f"Final result after retries: {await runner.get_result()}")

    async def post_run(self, runner) -> None:
        result = await runner.get_result()
        stdout = result.outputs.get("stdout", "")
        stderr = result.outputs.get("stderr", "")

        if not runner._format_typed_outputs(result):
            runner._log_output("stdout", stdout)

        runner._log_output("stderr", stderr)

        if runner.model.log_stdout and stdout and runner.ctx.output_path:
            runner._save_output_file(stdout, result.outputs)

        status_value = (
            RunnerStatus.COMPLETED.value
            if result.status == RunnerStatus.FINISHED
            else result.status.value
        )
        execution = build_step_execution_result(
            step_index=runner.model.step_index,
            name=runner.model.name,
            run_type=runner._run_type.value,
            status=status_value,
            error=result.error,
            outputs=result.outputs,
            duration_ms=runner.duration_ms(),
        )
        await runner.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())

        self._cleanup_outputs_file(runner)

        if runner.model.log_command:
            self._log_timeline(runner, result, status_value)

    async def on_failure(self, runner) -> None:
        try:
            result = await runner.get_result()
            execution = build_step_execution_result(
                step_index=runner.model.step_index,
                name=runner.model.name,
                run_type=runner._run_type.value,
                status=RunnerStatus.FAILED.value,
                error=result.error or runner._error,
                outputs=result.outputs,
                duration_ms=runner.duration_ms(),
            )
            await runner.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())
        except Exception as exc:
            runner._log_debug(f"Failed to save step execution on failure: {exc}")
        self._cleanup_outputs_file(runner)

    async def _apply_run_result(self, runner, res: RunResult) -> None:
        runner._error = res.error
        await runner.reg_set(RunnerRegistryKeys.OUTPUTS, res.outputs)
        await runner.reg_set(
            RunnerRegistryKeys.RESULT, res.model_dump(exclude={"outputs"})
        )

    def _log_timeline(self, runner, result: RunResult, status: str) -> None:
        from ofx.runner.timeline import log_step

        params = runner._build_timeline_params(result)
        log_step(
            ctx_vars=runner.ctx.vars,
            output_path=runner.ctx.output_path,
            step_name=runner.model.name or f"step{runner.model.step_index}",
            status=status,
            duration_ms=runner.duration_ms(),
            exit_code=result.outputs.get("exit_code"),
            **params,
        )

    def _cleanup_outputs_file(self, runner) -> None:
        if not runner._outputs_file:
            return
        with suppress(OSError):
            runner._outputs_file.unlink(missing_ok=True)

    def create_runner(self, runner) -> BaseRunner:
        runner_factory = getattr(runner, "_create_runner", None)
        if runner_factory is not None:
            return runner_factory()
        registry = getattr(runner, "_handler_registry", default_handler_registry)
        return registry.create_runner(runner._run_type, runner)
