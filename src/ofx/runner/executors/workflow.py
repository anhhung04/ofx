"""Executor for workflow runners."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ofx.runner.executors import Executor
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.settings import settings
from ofx.utils.workflow_utils import workflow_dirs_with_path

logger = logging.getLogger(settings.app_branding)


def build_profile_envs(profile) -> dict[str, str]:
    """Build runtime environment variables from an OFX profile."""
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
    return profile_envs


class WorkflowExecutor(Executor):
    @staticmethod
    def _activate_time_window(
        runner,
        window,
        *,
        denied_message: str,
        active_message: str | None = None,
    ) -> None:
        from ofx.profiles.time_window import TimeWindowGuard, check_time_window

        result = check_time_window(window)
        if not result["allowed"]:
            raise RuntimeError(f"Workflow aborted: {result['message']}. {denied_message}")

        if result["message"]:
            runner._log_warning(result["message"])

        runner._time_guard = TimeWindowGuard(
            window=window,
            on_warn=lambda msg: runner._log_warning(msg),
            on_abort=lambda msg: runner._log_error(
                f"🛑 {msg} - workflow will be aborted"
            ),
        )
        runner._time_guard.start()

        if active_message:
            runner._log_info(active_message)

    async def pre_run(self, runner) -> None:
        await runner._resolve_template_fields(
            ["name", "description", "tags", "env", "defaults"]
        )
        runner._log_debug(
            f"Resolved workflow: {runner.model.model_dump(exclude={'jobs'})}"
        )

        output_path = runner.ctx.output_path
        if output_path:
            output_path.mkdir(parents=True, exist_ok=True)

        runner._run_dir = Path(tempfile.mkdtemp(prefix="ofx_run_"))

        from ofx.runner.context import RunnerContextBuilder

        runner.ctx = RunnerContextBuilder(runner.ctx).with_env(
            {"OFX_RUN_DIR": str(runner._run_dir)}
        )
        runner.ctx = RunnerContextBuilder(runner.ctx).with_update(
            {
                "vars": {
                    **runner.ctx.vars,
                    "working_directory": runner.model.defaults.run.working_directory,
                },
                "workflow_dir": runner.model.workflow_path.parent,
            }
        )

        runner._log_debug(f"Workflow Dispatch: {runner.model.dispatch}")
        ctx_builder = RunnerContextBuilder(runner.ctx)
        if runner.model.dispatch and not runner._is_reused:
            runner.ctx = ctx_builder.with_inputs(
                await self.process_inputs(
                    runner,
                    runner.ctx.inputs,
                    runner.model.dispatch.inputs,
                )
            )

        self.expand_list_inputs_to_matrix(runner)

        runner._log_debug(f"Workflow Call: {runner.model.call}")
        if runner.model.call and runner._is_reused:
            runner.ctx = ctx_builder.with_inputs(
                await self.process_inputs(
                    runner,
                    runner.ctx.inputs,
                    runner.model.call.inputs,
                )
            )
            runner.ctx = RunnerContextBuilder(runner.ctx).with_secrets(
                await self.process_inputs(
                    runner,
                    runner.ctx.secrets,
                    runner.model.call.secrets,
                )
            )

            from ofx.utils.log import register_secrets

            register_secrets(runner.ctx.secrets)

        runner.ctx = RunnerContextBuilder(runner.ctx).with_update(
            {
                "workflow_dirs": workflow_dirs_with_path(
                    runner.ctx.workflow_dirs,
                    runner.model.defaults.workflows_base_dir.absolute(),
                )
            }
        )
        runner._log_debug(f"Processed context: {runner.ctx}")

        runner.ctx = RunnerContextBuilder(runner.ctx).with_env(runner.model.env)

        await self.apply_profile(runner)
        self.apply_cli_time_window(runner)

        await runner.reg_set(
            RunnerRegistryKeys.MODEL,
            runner.model.model_dump(exclude={"jobs", "env"}),
        )

        await self.install_tools(runner)

    async def do_run(self, runner) -> None:
        await self.plan_jobs(runner)
        await self.run_workflow(runner)

    async def post_run(self, runner) -> None:
        if runner._time_guard:
            runner._time_guard.stop()

        if runner._is_reused:
            job_runners = list(runner._runners.values())
            if any(job_runner.is_failed for job_runner in job_runners):
                failed_ids = [job.model.jid for job in job_runners if job.is_failed]
                raise RuntimeError(
                    f"Reusable workflow '{runner.model.name}': "
                    f"{len(failed_ids)}/{len(job_runners)} job(s) failed "
                    f"({', '.join(failed_ids)}). Cannot retrieve outputs."
                )
            if runner.model.call and runner.model.call.outputs:
                resolved_outputs = {}
                for key, value in runner.model.call.outputs.items():
                    resolved_outputs[key] = await runner._resolve_template(value)
                await runner.reg_set(RunnerRegistryKeys.OUTPUTS, resolved_outputs)

        await self.store_summaries(runner)
        runner._log_debug(f"result: {await runner.get_result()}")
        self._cleanup_run_dir(runner)

    async def on_failure(self, runner) -> None:
        self._cleanup_run_dir(runner)

    async def process_inputs(
        self,
        runner,
        req_inputs: dict,
        input_blueprint: dict,
    ) -> dict[str, Any]:
        runner._log_debug(
            f"Processing inputs: {req_inputs} with blueprint: {input_blueprint}"
        )

        def find_alias(alias: str | list[str] | None, names: set[str]) -> str | None:
            if not alias:
                return None
            if isinstance(alias, str):
                alias = [alias]
            for candidate in alias:
                if candidate in names:
                    return candidate
            return None

        req_inputs = dict(req_inputs)
        inputs_names = set(req_inputs.keys())

        for key, constraint in input_blueprint.items():
            alias = find_alias(constraint.alias, inputs_names)
            if key in req_inputs or alias:
                if alias:
                    if key in req_inputs:
                        runner._log_warning(
                            f"Both input '{key}' and its alias '{alias}' are provided. "
                            f"Using value from '{key}' and ignoring alias."
                        )
                        req_inputs.pop(alias)
                        continue
                    value = req_inputs[alias]
                    req_inputs[key] = value
                else:
                    value = req_inputs[key]

                if not self.check_input_type(value, constraint.type):
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
            req_inputs[key] = await runner._resolve_template(value)

        return req_inputs

    def check_input_type(self, value: Any, input_type: str) -> bool:
        if input_type == "string" and isinstance(value, list):
            return True

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

    def expand_list_inputs_to_matrix(self, runner) -> None:
        if not runner.model.dispatch or runner._is_reused:
            return

        matrix_inputs: dict[str, list] = {}
        for key, constraint in runner.model.dispatch.inputs.items():
            value = runner.ctx.inputs.get(key)
            if isinstance(value, list) and constraint.type == "string":
                matrix_inputs[key] = value

        if not matrix_inputs:
            return

        from ofx.models.strategy import MatrixStrategy

        for key, values in matrix_inputs.items():
            runner._log_info(
                f"Auto-expanding input '{key}' ({len(values)} values) as matrix"
            )
            for job in runner.model.jobs.values():
                if not self.job_references_input(job, key):
                    continue
                if not job.strategy:
                    job.strategy = MatrixStrategy.model_validate(
                        {"matrix": {key: values}}
                    )
                elif key not in job.strategy.matrix:
                    job.strategy.matrix[key] = values

        updated_inputs = runner.ctx.inputs.copy()
        for key in matrix_inputs:
            updated_inputs.pop(key, None)
        runner.ctx = runner.ctx.model_copy(
            update={
                "vars": {
                    **runner.ctx.vars,
                    "_matrix_input_keys": list(matrix_inputs.keys()),
                },
                "inputs": updated_inputs,
            }
        )

    @staticmethod
    def job_references_input(job, key: str) -> bool:
        needle = f"inputs.{key}"
        for step in job.steps:
            for field in (step.run, step.script, step.script_file):
                if field and needle in str(field):
                    return True
            if step.run_with:
                for value in step.run_with.values():
                    if needle in str(value):
                        return True
        return False

    async def apply_profile(self, runner) -> None:
        profile_name = runner.model.defaults.profile
        if not profile_name:
            return

        from ofx.profiles.manager import get_profile_manager

        mgr = get_profile_manager()
        profile = mgr.resolve_or_default(profile_name)
        if profile is None:
            return

        runner._profile = profile
        runner._log_info(f"Applying profile: {profile_name}")

        profile_envs = build_profile_envs(profile)
        runner.update_env_and_vars(
            (profile.env or {}) | profile_envs,
            {
                "profile": profile.model_dump(),
                "profile_model": profile,
            },
        )

        if profile.time_window.enabled:
            self._activate_time_window(
                runner,
                profile.time_window,
                denied_message=(
                    f"Profile '{profile_name}' restricts execution to "
                    f"{profile.time_window.start}–{profile.time_window.end} "
                    f"on {', '.join(day.title() for day in profile.time_window.days)} "
                    f"({profile.time_window.timezone})."
                ),
            )

    def apply_cli_time_window(self, runner) -> None:
        if runner._time_guard or runner._is_reused:
            return

        tw_str = runner.ctx.vars.get("_cli_time_window", "")
        if not tw_str or "-" not in tw_str:
            return

        parts = tw_str.split("-", 1)
        if len(parts) != 2:
            return

        from ofx.profiles.models import TimeWindow

        window = TimeWindow(
            enabled=True,
            start=parts[0].strip(),
            end=parts[1].strip(),
            abort_on_expire=True,
        )

        self._activate_time_window(
            runner,
            window,
            denied_message=(
                f"CLI --time-window restricts execution to {window.start}–{window.end}."
            ),
            active_message=f"Time window active: {window.start}–{window.end}",
        )

    async def install_tools(self, runner) -> None:
        tools = runner.model.tools
        if not tools:
            return

        from ofx.runner.tool_installer import ToolInstallerRunner

        installer = ToolInstallerRunner(
            tools=tools,
            ctx=runner._child_context(),
            parent=runner,
            show_console=False,
        )
        await installer.run()

    async def plan_jobs(self, runner) -> None:
        from ofx.runner.workflow_scheduler import WorkflowScheduler

        schedule = WorkflowScheduler(runner.model.jobs).plan()
        runner._staged_jobs = schedule.staged_jobs
        runner._schedule = schedule.schedule
        runner._log_debug(f"Stages: {runner._schedule}")

    async def run_workflow(self, runner) -> None:
        from ofx.runner.workflow_execution import WorkflowExecutionManager

        result = await WorkflowExecutionManager(runner).run(
            runner._schedule,
            runner._staged_jobs,
        )
        failed_job_ids = result.failed_job_ids
        failed_stage_indices = result.failed_stage_indices

        if failed_job_ids:
            from ofx.runner.error_helpers import extract_root_error
            from ofx.runner.runner import BaseRunner

            for job_runner in runner._runners.values():
                if isinstance(job_runner, BaseRunner):
                    try:
                        await job_runner._post_run()
                    except Exception as exc:
                        runner._log_debug(
                            f"post_run cleanup failed for {job_runner.model.jid}: {exc}"
                        )
            await self.store_summaries(runner)

            concise_lines = []
            for job_id in failed_job_ids:
                failed_runner = runner._runners.get(job_id)
                root = extract_root_error(
                    failed_runner._error if failed_runner else None
                )
                concise_lines.append(f"job '{job_id}': {root}")

            error_msg = "Job failure(s):\n" + "\n".join(concise_lines)
            await runner.reg_set(
                RunnerRegistryKeys.ERRORS,
                {
                    "message": error_msg,
                    "failed_jobs": failed_job_ids,
                    "failed_stages": failed_stage_indices,
                },
            )
            raise RuntimeError(error_msg)

    async def store_summaries(self, runner) -> None:
        from ofx.runner.execution_summary import ExecutionSummaryReporter

        reporter = ExecutionSummaryReporter(runner)
        summary = await reporter.build()
        unified = await reporter.build_unified()

        if runner._time_guard:
            from ofx.profiles.time_window import check_time_window

            time_window = runner._time_guard._window
            time_window_result = check_time_window(time_window)
            unified["time_window"] = {
                "start": time_window.start,
                "end": time_window.end,
                "remaining_minutes": time_window_result.get("remaining_minutes"),
                "aborted": runner._time_guard.should_abort,
            }

        await runner.reg_set(RunnerRegistryKeys.SUMMARY, summary.to_dict())
        await runner.reg_set(RunnerRegistryKeys.SUMMARY_UNIFIED, unified)
        existing_outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
        existing_outputs["__summary__"] = unified
        await runner.reg_set(RunnerRegistryKeys.OUTPUTS, existing_outputs)
        await self.auto_export_findings(runner, existing_outputs)

    async def auto_export_findings(self, runner, existing_outputs: dict) -> None:
        project_path = runner.ctx.vars.get("project_path")
        if not project_path:
            return

        try:
            from ofx.runner.findings_export import auto_export_findings

            summaries = await auto_export_findings(
                runner._runners,
                project_path,
                log_fn=runner._log_info,
            )
            if summaries:
                existing_outputs["__findings_export__"] = summaries
                await runner.reg_set(RunnerRegistryKeys.OUTPUTS, existing_outputs)
        except Exception as exc:
            runner._log_debug(f"Findings export failed: {exc}")

    def _cleanup_run_dir(self, runner) -> None:
        run_dir = getattr(runner, "_run_dir", None)
        if run_dir and run_dir.exists():
            try:
                shutil.rmtree(run_dir)
            except Exception as exc:
                logger.debug("Failed to clean up run dir %s: %s", run_dir, exc)
