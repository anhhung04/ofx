"""Workflow runner for parallel job execution and workflow orchestration"""

import logging
from typing import Any

from ofx.models.workflow import Workflow
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import BaseRunner, RegistryAdapter, RunContext, RunnerRegistryKeys
from ofx.runner.execution.cloud_job import CloudJobRunner
from ofx.runner.execution.execution_summary import ExecutionSummaryReporter
from ofx.runner.execution.job import JobRunner, MatrixJobRunner
from ofx.runner.execution.tool_installer import ToolInstallerRunner
from ofx.runner.execution.workflow_execution import WorkflowExecutionManager
from ofx.runner.execution.workflow_scheduler import WorkflowScheduler
from ofx.settings import settings
from ofx.utils.workflow_utils import add_workflow_dir

logger = logging.getLogger(settings.app_branding)


class WorkflowRunner(BaseRunner[Workflow]):
    def __init__(
        self,
        workflow: Workflow,
        ctx: RunContext,
        parent: BaseRunner | None = None,
        registry: RegistryAdapter | None = None,
    ):
        super().__init__(workflow, ctx, parent, registry)
        self._is_reused = self.parent is not None
        if not self._is_reused:
            self.name = f"[RUN-{self.run_id}]:{self.name}"
        self._profile = None
        self._time_guard = None

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(
            ["name", "description", "tags", "env", "defaults"]
        )
        self._log_debug(f"Resolved workflow: {self.model.model_dump(exclude={'jobs'})}")

        output_path = self.ctx.output_path
        if output_path:
            output_path.mkdir(parents=True, exist_ok=True)
        self.ctx.vars["working_directory"] = self.model.defaults.run.working_directory
        self.ctx = RunnerContextBuilder(self.ctx).with_update(
            {"workflow_dir": self.model.workflow_path.parent}
        )

        self._log_debug(f"Workflow Dispatch: {self.model.dispatch}")
        ctx_builder = RunnerContextBuilder(self.ctx)
        if self.model.dispatch and not self._is_reused:
            self.ctx = ctx_builder.with_inputs(
                await self._process_inputs(self.ctx.inputs, self.model.dispatch.inputs)
            )

        # ── Auto-matrix expansion for list inputs ──────────────────
        self._expand_list_inputs_to_matrix()

        self._log_debug(f"Workflow Call: {self.model.call}")
        if self.model.call and self._is_reused:
            self.ctx = ctx_builder.with_inputs(
                await self._process_inputs(self.ctx.inputs, self.model.call.inputs)
            )
            self.ctx = RunnerContextBuilder(self.ctx).with_secrets(
                await self._process_inputs(self.ctx.secrets, self.model.call.secrets)
            )
            # Register call-injected secrets for log redaction.
            from ofx.utils.log import register_secrets

            register_secrets(self.ctx.secrets)

        self.ctx = ctx_builder.with_update(
            {
                "workflow_dirs": add_workflow_dir(
                    self.ctx.workflow_dirs,
                    self.model.defaults.workflows_base_dir.absolute(),
                )
            }
        )
        self._log_debug(f"Processed context: {self.ctx}")

        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)

        # ── Profile resolution ─────────────────────────────────────
        await self._apply_profile()

        # ── CLI time window override ──────────────────────────────
        self._apply_cli_time_window()

        await self.reg_set(
            RunnerRegistryKeys.MODEL, self.model.model_dump(exclude={"jobs", "env"})
        )

        await self._install_tools()

    async def _do_run(self) -> None:
        await self._plan_jobs()
        await self._run_workflow()

    async def _post_run(self) -> None:
        # Stop time-window guard
        if self._time_guard:
            self._time_guard.stop()

        if self._is_reused:
            job_runners = self._runners.values()
            if any(runner.is_failed for runner in job_runners):
                raise RuntimeError(
                    f"Reusable workflow '{self.model.name}' has failed jobs. Cannot retrieve outputs."
                )
            # Handle call outputs for reusable workflows
            if self.model.call and self.model.call.outputs:
                resolved_outputs = {}
                for key, value in self.model.call.outputs.items():
                    resolved_value = await self._resolve_template(value)
                    resolved_outputs[key] = resolved_value
                await self.reg_set(RunnerRegistryKeys.OUTPUTS, resolved_outputs)

        # Save job results to registry for additional data access
        job_results = {}
        for job_id, runner in self._runners.items():
            result = await runner.get_result()
            job_results[job_id] = result.model_dump()
        await self.reg_set_global("jobs:results", job_results)
        await self._store_summaries()
        self._log_debug(f"result: {await self.get_result()}")

    async def _run_workflow(self) -> None:
        execution = WorkflowExecutionManager(self)
        result = await execution.run(self._schedule, self._staged_jobs)
        if result.failed_job_ids:
            # Ensure job execution data is present before summarizing
            for runner in self._runners.values():
                if isinstance(runner, (JobRunner, MatrixJobRunner, CloudJobRunner)):
                    try:
                        await runner._post_run()
                    except Exception as e:
                        logger.debug("post_run cleanup failed for %s: %s", runner.model.jid, e)
            await self._store_summaries()

            # Build concise error: one line per failed job with root cause
            from ofx.runner.execution.error_helpers import extract_root_error

            concise_lines = []
            for job_id in result.failed_job_ids:
                runner = self._runners.get(job_id)
                root = extract_root_error(runner._error if runner else None)
                concise_lines.append(f"job '{job_id}': {root}")

            error_msg = "Job failure(s):\n" + "\n".join(concise_lines)
            await self.reg_set(
                RunnerRegistryKeys.ERRORS,
                {
                    "message": error_msg,
                    "failed_jobs": result.failed_job_ids,
                    "failed_stages": result.failed_stage_indices,
                },
            )
            raise RuntimeError(error_msg)

    async def _plan_jobs(self) -> None:
        schedule = WorkflowScheduler(self.model.jobs).plan()
        self._staged_jobs = schedule.staged_jobs
        self._schedule = schedule.schedule
        self._log_debug(f"Stages: {self._schedule}")

    async def _store_summaries(self) -> None:
        reporter = ExecutionSummaryReporter(self)
        summary = await reporter.build()
        unified = await reporter.build_unified()

        # Inject time window metadata if active
        if self._time_guard:
            from ofx.profiles.time_window import check_time_window

            tw = self._time_guard._window
            tw_result = check_time_window(tw)
            unified["time_window"] = {
                "start": tw.start,
                "end": tw.end,
                "remaining_minutes": tw_result.get("remaining_minutes"),
                "aborted": self._time_guard.should_abort,
            }

        await self.reg_set(RunnerRegistryKeys.SUMMARY, summary.to_dict())
        await self.reg_set(RunnerRegistryKeys.SUMMARY_UNIFIED, unified)
        # Expose unified summary in outputs for CLI consumption
        existing = await self.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
        existing["__summary__"] = unified
        await self.reg_set(RunnerRegistryKeys.OUTPUTS, existing)

        # Auto-export findings to project directory
        await self._auto_export_findings(existing)

    async def _auto_export_findings(self, existing_outputs: dict) -> None:
        """Export typed findings to the project directory when --project is set."""
        project_path = self.ctx.vars.get("project_path")
        if not project_path:
            return

        try:
            from ofx.runner.execution.findings_export import auto_export_findings

            summaries = await auto_export_findings(
                self._runners,
                project_path,
                log_fn=self._log_info,
            )
            if summaries:
                existing_outputs["__findings_export__"] = summaries
                await self.reg_set(RunnerRegistryKeys.OUTPUTS, existing_outputs)
        except Exception as e:
            self._log_debug(f"Findings export failed: {e}")

    async def _install_tools(self) -> None:
        tools = self.model.tools
        if not tools:
            return

        installer = ToolInstallerRunner(
            tools=tools,
            ctx=self._child_context(),
            parent=self,
            show_console=False,
        )
        await installer.run()

    # ── Profile & Time Window ──────────────────────────────────────

    async def _apply_profile(self) -> None:
        """Load the named profile and apply its settings."""
        profile_name = self.model.defaults.profile
        if not profile_name:
            return

        from ofx.profiles.manager import get_profile_manager

        mgr = get_profile_manager()
        profile = mgr.resolve_or_default(profile_name)
        if profile is None:
            return

        self._profile = profile
        self._log_info(f"Applying profile: {profile_name}")

        # Inject profile env vars into context
        if profile.env:
            self.ctx = RunnerContextBuilder(self.ctx).with_env(profile.env)

        # Inject key profile fields as OFX_* env vars for tool consumption
        profile_envs: dict[str, str] = {}
        if profile.rate_limit:
            profile_envs["OFX_RATE_LIMIT"] = str(profile.rate_limit)
        if profile.threads != 10:
            profile_envs["OFX_THREADS"] = str(profile.threads)
        if profile.timeout_minutes != 60:
            profile_envs["OFX_TIMEOUT"] = str(profile.timeout_minutes)
        if profile.delay:
            profile_envs["OFX_DELAY"] = str(profile.delay)
        if profile.jitter:
            profile_envs["OFX_JITTER"] = str(profile.jitter)
        if profile.proxy:
            profile_envs["OFX_PROXY"] = profile.proxy
        if profile.user_agent:
            profile_envs["OFX_USER_AGENT"] = profile.user_agent
        if profile_envs:
            self.ctx = RunnerContextBuilder(self.ctx).with_env(profile_envs)

        # Store profile data so steps/tasks can access it via templates
        self.ctx.vars["profile"] = profile.model_dump()
        # Preserve profile model for runtime logic that needs typed access
        self.ctx.vars["profile_model"] = profile

        # ── Time window enforcement ────────────────────────────────
        if profile.time_window.enabled:
            from ofx.profiles.time_window import TimeWindowGuard, check_time_window

            result = check_time_window(profile.time_window)
            if not result["allowed"]:
                raise RuntimeError(
                    f"Workflow aborted: {result['message']}. "
                    f"Profile '{profile_name}' restricts execution to "
                    f"{profile.time_window.start}–{profile.time_window.end} "
                    f"on {', '.join(d.title() for d in profile.time_window.days)} "
                    f"({profile.time_window.timezone})."
                )

            if result["message"]:
                self._log_warning(result["message"])

            # Start background monitor
            self._time_guard = TimeWindowGuard(
                window=profile.time_window,
                on_warn=lambda msg: self._log_warning(msg),
                on_abort=lambda msg: self._log_error(
                    f"🛑 {msg} — workflow will be aborted"
                ),
            )
            self._time_guard.start()

    def _apply_cli_time_window(self) -> None:
        """Apply a time window from CLI --time-window flag (HH:MM-HH:MM)."""
        if self._time_guard or self._is_reused:
            return  # Profile already set a guard, or this is a reusable workflow

        tw_str = self.ctx.vars.get("_cli_time_window", "")
        if not tw_str or "-" not in tw_str:
            return

        parts = tw_str.split("-", 1)
        if len(parts) != 2:
            return

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import TimeWindowGuard, check_time_window

        window = TimeWindow(
            enabled=True,
            start=parts[0].strip(),
            end=parts[1].strip(),
            abort_on_expire=True,
        )

        result = check_time_window(window)
        if not result["allowed"]:
            raise RuntimeError(
                f"Workflow aborted: {result['message']}. "
                f"CLI --time-window restricts execution to {window.start}–{window.end}."
            )

        if result["message"]:
            self._log_warning(result["message"])

        self._time_guard = TimeWindowGuard(
            window=window,
            on_warn=lambda msg: self._log_warning(msg),
            on_abort=lambda msg: self._log_error(
                f"🛑 {msg} — workflow will be aborted"
            ),
        )
        self._time_guard.start()
        self._log_info(f"Time window active: {window.start}–{window.end}")

    # ── Input processing ───────────────────────────────────────────

    async def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> dict[str, Any]:
        self._log_debug(
            f"Processing inputs: {req_inputs} with blueprint: {input_blueprint}"
        )

        def find_alias(alias: str | list[str] | None, names: set[str]) -> str | None:
            if not alias:
                return None
            if isinstance(alias, str):
                alias = [alias]
            for a in alias:
                if a in names:
                    return a
            return None

        inputs_names = set(req_inputs.keys())

        for key, constraint in input_blueprint.items():
            alias = find_alias(constraint.alias, inputs_names)
            if key in req_inputs or alias:
                value = None
                if alias:
                    if key in req_inputs:
                        self._log_warning(
                            f"Both input '{key}' and its alias '{alias}' are provided. "
                            f"Using value from '{key}' and ignoring alias."
                        )
                        req_inputs.pop(alias)
                        continue
                    else:
                        value = req_inputs[alias]
                        req_inputs[key] = value
                else:
                    value = req_inputs[key]
                # Allow list values for string-type inputs (matrix-expanded later)
                if isinstance(value, list) and constraint.type == "string":
                    pass
                elif not self._check_input_type(value, constraint.type):
                    raise ValueError(
                        f"Input '{key}' has invalid type: {type(value).__name__}. "
                        f"Expected type: {constraint.type}."
                    )
            else:
                if constraint.required:
                    raise ValueError(
                        f"Input '{key}' is required but not provided in the inputs."
                    )
                req_inputs[key] = constraint.default
        for key, value in req_inputs.items():
            req_inputs[key] = await self._resolve_template(value)

        return req_inputs

    def _check_input_type(self, value: Any, input_type: str) -> bool:
        type_map = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_type = type_map.get(input_type)
        if expected_type is None:
            raise ValueError(
                f"Unsupported input type '{input_type}' for value '{value}'. "
                f"Supported types are: {', '.join(type_map.keys())}."
            )
        return isinstance(value, expected_type)

    def _expand_list_inputs_to_matrix(self) -> None:
        """Auto-inject matrix strategy when an input is a list.

        When a dispatch input declared as ``type: string`` receives a list
        (e.g. multiple targets from ``@file`` or the targets folder), inject
        each list value as a matrix dimension on every job.  The original
        input key is stored in ``ctx.vars["_matrix_input_keys"]`` so that
        ``MatrixJobRunner`` can override ``inputs.<key>`` per combination.
        """
        if not self.model.dispatch or self._is_reused:
            return

        matrix_inputs: dict[str, list] = {}
        for key, constraint in self.model.dispatch.inputs.items():
            value = self.ctx.inputs.get(key)
            if isinstance(value, list) and constraint.type == "string":
                matrix_inputs[key] = value

        if not matrix_inputs:
            return

        from ofx.models.strategy import MatrixStrategy

        for key, values in matrix_inputs.items():
            self._log_info(
                f"Auto-expanding input '{key}' ({len(values)} values) as matrix"
            )
            for job in self.model.jobs.values():
                # Only inject matrix on jobs that reference the input key in
                # their step definitions (run/script/with fields).  Downstream
                # jobs that depend on earlier results should not be expanded.
                if not self._job_references_input(job, key):
                    continue
                if not job.strategy:
                    job.strategy = MatrixStrategy(matrix={key: values})
                elif key not in job.strategy.matrix:
                    job.strategy.matrix[key] = values

        # Store which input keys are matrix-expanded so runners
        # can propagate matrix values back into inputs per combination.
        self.ctx.vars["_matrix_input_keys"] = list(matrix_inputs.keys())
        # Remove list values from inputs — they live in matrix now.
        for key in matrix_inputs:
            del self.ctx.inputs[key]

    @staticmethod
    def _job_references_input(job, key: str) -> bool:
        """Check if a job's steps reference ``inputs.<key>`` in any template field."""
        needle = f"inputs.{key}"
        for step in job.steps:
            for field in (step.run, step.script, step.script_file):
                if field and needle in str(field):
                    return True
            if step.run_with:
                for v in step.run_with.values():
                    if needle in str(v):
                        return True
        return False

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        prefix = f"'{self.model.name}'"
        if self.parent:
            return self.parent._produce_log(f"{prefix} › {message_str}")
        return f"{prefix} › {message_str}"

    @property
    def runners(self) -> dict[str, JobRunner | MatrixJobRunner]:
        """Get the job runners within the workflow"""
        job_runners = {}
        for k, v in self._runners.items():
            if isinstance(v, (JobRunner, MatrixJobRunner)):
                job_runners[k] = v
        return job_runners
