"""Executor for workflow step runners."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ofx.models.step import RunType
from ofx.runner.core.models import RunnerStatus, RunResult
from ofx.runner.core.registry_keys import RunnerRegistryKeys
from ofx.runner.executors import Executor
if TYPE_CHECKING:
    from ofx.runner.core.base import BaseRunner


class StepExecutor(Executor):
    async def pre_run(self, runner) -> None:
        return None

    async def do_run(self, runner) -> None:
        max_attempts = runner.model.retry + 1
        timeout_seconds = self._timeout_int(runner.model.timeout) * 60

        last_res = None
        attempt_errors: list[str] = []

        for attempt in range(max_attempts):
            try:
                child_runner = runner._create_runner()
                res = await asyncio.wait_for(
                    child_runner.run(), timeout=timeout_seconds
                )
                last_res = res

                if child_runner.is_success:
                    await self._apply_run_result(runner, res)
                    runner._log_debug(f"result: {await runner.get_result()}")
                    return

                raise RuntimeError(self._step_execution_error(res.status, res.error))
            except TimeoutError as exc:
                raise RuntimeError(
                    self._step_timeout_error(self._timeout_int(runner.model.timeout))
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
                                self._step_retry_error(max_attempts, last_res.error)
                                + f"\n  Attempts: {'; '.join(attempt_errors)}"
                            ) from exc
                    else:
                        raise RuntimeError(
                            self._step_retry_error(max_attempts, exc)
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
        execution = self._build_step_execution_result(
            step_index=runner.model.step_index,
            name=runner.model.name,
            run_type=runner._run_type.value,
            status=status_value,
            error=result.error,
            outputs=result.outputs,
            duration_ms=runner.duration_ms(),
        )
        await runner.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())

        if runner._outputs_file:
            runner._outputs_file.unlink(missing_ok=True)

        if runner.model.log_command:
            runner._log_timeline(result, status_value)

    async def on_failure(self, runner) -> None:
        try:
            result = await runner.get_result()
            execution = self._build_step_execution_result(
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
        if runner._outputs_file:
            runner._outputs_file.unlink(missing_ok=True)

    def _timeout_int(self, timeout) -> int:
        from ofx.runner.execution.step import _timeout_int

        return _timeout_int(timeout)

    def _step_execution_error(self, status, error) -> str:
        from ofx.runner.execution.error_helpers import step_execution_error

        return step_execution_error(status, error)

    def _step_retry_error(self, max_attempts: int, error) -> str:
        from ofx.runner.execution.error_helpers import step_retry_error

        return step_retry_error(max_attempts, error)

    def _step_timeout_error(self, timeout) -> str:
        from ofx.runner.execution.error_helpers import step_timeout_error

        return step_timeout_error(timeout)

    def _build_step_execution_result(self, **kwargs):
        from ofx.runner.execution.execution_results import build_step_execution_result

        return build_step_execution_result(**kwargs)

    async def _apply_run_result(self, runner, res: RunResult) -> None:
        runner._error = res.error
        await runner.reg_set(RunnerRegistryKeys.OUTPUTS, res.outputs)
        await runner.reg_set(
            RunnerRegistryKeys.RESULT, res.model_dump(exclude={"outputs"})
        )

    def create_runner(self, runner) -> BaseRunner:
        if (
            runner.model.interactive
            and runner.ctx.allow_interactive
            and runner._run_type == RunType.WORKFLOW
        ):
            runner._log_warning(
                "Interactive mode is not supported for workflow steps ('uses'). Ignoring interactive flag."
            )
        from ofx.runner.handlers import get_handler_registry

        return get_handler_registry().create(runner._run_type, runner)
