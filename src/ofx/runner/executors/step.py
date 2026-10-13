"""Executor for workflow step runners."""

from __future__ import annotations

import asyncio
import logging

from ofx.models.step import RunType
from ofx.runner.context import (
    ConditionNotMetError,
    RunnerStatus,
    RunResult,
    context_copy,
    normalized_runner_status_value,
)
from ofx.runner.error_helpers import (
    coerce_timeout_minutes,
    step_execution_error,
    step_retry_error,
    step_timeout_error,
)
from ofx.runner.execution_results import build_step_execution_result_for_runner
from ofx.runner.executors.base import Executor
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.utils.file_cleanup import remove_file


def _create_step_child_runner(step_runner):
    """Build the child runner for a step's run type (module/workflow/pipe).

    Direct dispatch replaces the legacy ``HandlerRegistry``: the run-type set
    is closed (``RunType``), and cloud steps use the ``_create_runner``
    duck-type hook instead.
    """
    run_type = step_runner._run_type
    if run_type == RunType.MODULE:
        from ofx.modules import ModuleInvocation, ModuleRunner
        from ofx.runner.run_defaults import resolve_model_shell

        invocation = ModuleInvocation(
            name=step_runner.model.module,
            # `with:` args were already template-resolved and merged into
            # ctx.inputs by StepRunner._pre_run — that merged view is the
            # single source of truth for module arguments.
            args=dict(step_runner.ctx.inputs),
            timeout_minutes=step_runner.model.timeout,
            shell=resolve_model_shell(step_runner, step_runner.model),
            working_directory=step_runner._resolve_working_dir(),
            interactive=step_runner.model.interactive and step_runner.ctx.allow_interactive,
        )
        return ModuleRunner(
            invocation,
            context_copy(step_runner.ctx),
            parent=step_runner,
        )
    if run_type == RunType.WORKFLOW:
        from ofx.runner.workflow import WorkflowRunner
        from ofx.utils.workflow_utils import find_workflow, workflow_dirs_with_path

        parent_workflow_dir = (
            step_runner.ctx.workflow_dir
            or step_runner.parent.model.workflow_path.parent
        )
        search_dirs = workflow_dirs_with_path(
            step_runner.ctx.workflow_dirs,
            parent_workflow_dir,
        )
        workflow = find_workflow(
            step_runner.model.uses or "",
            tuple(search_dirs),
            step_runner.parent.model.defaults.flow_registry_url,
        )
        return WorkflowRunner(
            workflow,
            context_copy(
                step_runner.ctx,
                update={
                    "workflow_dirs": workflow_dirs_with_path(
                        search_dirs, workflow.workflow_path.parent
                    ),
                },
            ),
            parent=step_runner,
        )
    if run_type == RunType.PIPE:
        from ofx.runner.pipe import PipeExecution, PipeRunner

        model = PipeExecution(pipe=step_runner.model.pipe)
        return PipeRunner(
            model,
            context_copy(step_runner.ctx),
            parent=step_runner,
        )
    raise ValueError(f"Invalid run type '{run_type}'. No step child runner for it.")


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
            timed_out = False
            last_exc: BaseException | None = None
            try:
                if (
                    getattr(runner.model, "interactive", False)
                    and getattr(runner.ctx, "allow_interactive", False)
                    and runner._run_type == RunType.WORKFLOW
                ):
                    runner._log_warning(
                        "Interactive mode is not supported for workflow steps ('uses'). "
                        "Ignoring interactive flag."
                    )
                runner_factory = getattr(runner, "_create_runner", None)
                if runner_factory is not None:
                    child_runner = runner_factory()
                else:
                    child_runner = _create_step_child_runner(runner)
                # Cloud remote handlers expose a network grace budget on the
                # child (H5): extend the outer wrapper's wait so the grace is
                # actually reachable (local children expose no grace -> 0).
                network_grace = getattr(child_runner, "_network_grace_seconds", 0)
                res = await asyncio.wait_for(
                    child_runner.run(),
                    timeout=timeout_seconds + network_grace,
                )
                last_res = res

                # A child that finished as CANCELED must not be retried (L11):
                # propagate the cancellation/skip immediately.
                if res.status == RunnerStatus.CANCELED:
                    raise ConditionNotMetError(
                        res.error
                        or "Step was canceled before completion; skipping without retry"
                    )

                if child_runner.is_success:
                    await self._store_child_result(runner, res)
                    # gate the deep-copying get_result() behind debug logging (L6)
                    if getattr(runner, "_log_level", logging.DEBUG) <= logging.DEBUG:
                        runner._log_debug(f"result: {await runner.get_result()}")
                    return

                raise RuntimeError(step_execution_error(res.status, res.error))
            except TimeoutError as exc:
                # Timeouts count as a retryable attempt (H4): record the error
                # and fall through to the shared retry logic below; only the
                # final attempt raises the timeout-specific error.
                timed_out = True
                last_exc = exc
                err_msg = step_timeout_error(coerce_timeout_minutes(runner.model.timeout))
            except ConditionNotMetError:
                # Cancellation/skip propagates immediately (L11) — no retry.
                raise
            except Exception as exc:
                last_exc = exc
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
            if timed_out:
                raise RuntimeError(
                    step_timeout_error(coerce_timeout_minutes(runner.model.timeout))
                    + attempts_suffix
                ) from last_exc
            if last_res:
                await self._store_child_result(runner, last_res)
                if last_res.status != RunnerStatus.COMPLETED:
                    raise RuntimeError(
                        step_retry_error(max_attempts, last_res.error)
                        + attempts_suffix
                    ) from last_exc

            raise RuntimeError(
                step_retry_error(max_attempts, last_exc)
                + attempts_suffix
            ) from last_exc

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
            from ofx.runner.timeline import log_step_async

            params = runner._build_timeline_params(result)
            await log_step_async(
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
