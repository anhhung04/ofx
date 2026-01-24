"""Job runner for orchestrating step execution"""

import asyncio
import itertools
import logging
from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.core import BaseRunner, RunContext, RunnerStatus, RunResult
from ofx.runner.core.registries import RegistryAdapter
from ofx.runner.executors.step import StepRunner
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class JobRunner(BaseRunner[Job]):
    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
    ):
        super().__init__(job, ctx, parent, parent.registry)
        self._processed_steps = 0

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(
            ["name", "needs", "run_if", "env", "defaults"]
        )
        self.ctx.envs.update(self.model.env)
        logger.debug(
            self._produce_log(
                f"Resolved job: {self.model.model_dump(exclude={'steps'})}"
            )
        )
        if isinstance(self.model.needs, str):
            self.model.needs = [self.model.needs]
        unmet_deps = []
        runners: dict[str, JobRunner] = self.parent.runners  # type: ignore
        for job_id in self.model.needs:
            if self.parent and not runners[job_id].is_success:
                unmet_deps.append(job_id)
        if len(unmet_deps) > 0:
            raise RuntimeError(
                f"Job cannot run because dependencies are not met: {unmet_deps}"
            )
        if not eval(str(self.model.run_if)):
            raise RuntimeError(self._produce_log("Job condition is not met"))
        # TODO: add needs data resolve

    async def _do_run(self) -> None:
        for step in self.model.steps:
            step_ctx = self.ctx.model_copy(
                update={
                    "secrets": self.ctx.secrets if step.secrets != "inherit" else {},
                },
                deep=True,
            )

            step_runner = StepRunner(
                step,
                step_ctx,
                self,
            )
            result = await step_runner.run()
            # step_id = step.step_index
            # dump_model = result.model_dump()
            # TODO: add registry handler for step
            self._processed_steps += 1
            if not step_runner.is_success and not step.continue_on_error:
                raise RuntimeError(
                    f"Step '{step.name or step.step_index}' failed: {result.error}"
                )

    async def _post_run(self) -> None:
        # TODO: add handle step outputs
        if self.model.outputs:
            for key, value in self.model.outputs.items():
                pass
        logger.debug(
            self._produce_log(
                f"job '{self.model.name or self.model.jid}' result: {await self.get_result()}"
            )
        )

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"'{self.model.jid}' › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def processed_steps(self) -> int:
        return self._processed_steps

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)


class MatrixJobRunner(BaseRunner[Job]):
    """Runner for jobs with matrix strategy, handling multiple matrix combinations"""

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
    ):
        super().__init__(job, ctx, parent)
        self.name = f"Matrix{self.name}"

    async def _do_run(self) -> None:
        """Run all matrix combinations with optional parallelism limit"""
        if not self._matrix_combinations:
            self._state_machine.transition(RunnerStatus.COMPLETED)
            return

        strategy = self.model.strategy
        max_parallel = (
            strategy.max_parallel if strategy else len(self._matrix_combinations)
        )

        semaphore = asyncio.Semaphore(max_parallel)

        async def run_instance(matrix_idx: int, matrix_values: dict[str, Any]):
            async with semaphore:
                return await self._run_single_job(matrix_idx, matrix_values)

        tasks = [
            asyncio.create_task(run_instance(idx, combo))
            for idx, combo in enumerate(self._matrix_combinations)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        failed = False
        errors = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed = True
                errors.append(f"Matrix combination {i}: {result}")
            elif (
                isinstance(result, RunResult)
                and result.status != RunnerStatus.COMPLETED
            ):
                failed = True
                errors.append(f"Matrix combination {i}: {result.error or 'Failed'}")

        if failed:
            self._state_machine.transition(RunnerStatus.FAILED)
            self._error = "; ".join(errors)
        else:
            self._state_machine.transition(RunnerStatus.COMPLETED)

    async def _run_single_job(self, matrix_idx: int, matrix_values: dict[str, Any]):
        """Run a single job instance with specific matrix values"""
        job_ctx = self.ctx.model_copy(deep=True)
        job_ctx.vars["matrix"] = matrix_values

        runner = JobRunner(
            self.model.model_copy(
                update={
                    "name": f"{self.model.name}{{{str(matrix_idx)}}}",
                    "jid": f"{self.model.jid}_{str(matrix_idx)}",
                    "matrix_values": matrix_values,
                    "matrix_index": matrix_idx,
                },
            ),
            job_ctx,
            parent=self.parent,  # type: ignore
        )
        return await runner.run()

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(["strategy"])
        self._matrix_combinations = self._generate_matrix_combinations()

    async def _post_run(self) -> None:
        pass

    def _generate_matrix_combinations(self) -> list[dict[str, Any]]:
        """Generate all matrix combinations with include/exclude rules"""
        strategy = self.model.strategy
        if not strategy or not strategy.matrix:
            return []

        matrix_keys = list(strategy.matrix.keys())
        matrix_values = [strategy.matrix[key] for key in matrix_keys]

        base_combinations = [
            dict(zip(matrix_keys, combination, strict=True))
            for combination in itertools.product(*matrix_values)
        ]

        def _matches_matrix_filter(
            combo: dict[str, Any], filters: list[dict[str, Any]]
        ) -> bool:
            """Check if a combination matches any filter"""
            for filter_dict in filters:
                if all(combo.get(key) == value for key, value in filter_dict.items()):
                    return True
            return False

        if strategy.exclude:
            base_combinations = [
                combo
                for combo in base_combinations
                if not _matches_matrix_filter(combo, strategy.exclude)
            ]

        if strategy.include:
            for include_combo in strategy.include:
                if include_combo not in base_combinations:
                    base_combinations.append(include_combo)

        return base_combinations
