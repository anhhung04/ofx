"""Shared helpers for JobRunner and CloudJobRunner.

Extracted to eliminate code duplication between local and cloud job
execution paths.
"""

from __future__ import annotations

from ofx.runner.core import (
    BaseRunner,
    ConditionNotMetError,
    RunnerRegistryKeys,
    RunnerStatus,
)
from ofx.runner.execution.execution_results import (
    build_job_execution_result,
    build_run_if_context,
)


class JobRunnerMixin:
    """Mixin providing methods shared by JobRunner and CloudJobRunner."""

    def _check_dependencies_and_run_if(self) -> None:
        """Validate job dependencies and evaluate run_if condition.

        Shared logic between JobRunner._pre_run and CloudJobRunner._pre_run.
        """
        if isinstance(self.model.needs, str):  # type: ignore[attr-defined]
            self.model.needs = [self.model.needs]  # type: ignore[attr-defined]

        runners: dict[str, BaseRunner] = self.parent.runners  # type: ignore[attr-defined]
        dep_runners = []
        for job_id in self.model.needs:  # type: ignore[attr-defined]
            runner = runners.get(job_id)
            if not runner:
                raise RuntimeError(
                    f"Job dependency '{job_id}' is missing from workflow runners."
                )
            dep_runners.append(runner)

        run_if_expr = self.model.run_if  # type: ignore[attr-defined]
        if run_if_expr is True and dep_runners:
            run_if_expr = "success()"

        if not self._evaluate_run_if(run_if_expr, build_run_if_context(dep_runners)):  # type: ignore[attr-defined]
            self._state_machine.transition(RunnerStatus.CANCELED)  # type: ignore[attr-defined]
            raise ConditionNotMetError(self._produce_log("Job condition is not met"))  # type: ignore[attr-defined]

    async def _save_job_results(self) -> None:
        """Resolve job outputs and save execution result to registry.

        Shared logic between JobRunner._post_run and CloudJobRunner._post_run.
        """
        resolved_outputs = await self._resolve_job_outputs()  # type: ignore[attr-defined]
        if resolved_outputs:
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, resolved_outputs)  # type: ignore[attr-defined]

        job_exec = build_job_execution_result(self, self._runners)  # type: ignore[attr-defined]
        await self.reg_set(RunnerRegistryKeys.EXECUTION, job_exec.to_dict())  # type: ignore[attr-defined]

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)  # type: ignore[attr-defined]
