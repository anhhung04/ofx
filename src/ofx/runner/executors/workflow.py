"""Executor for workflow runners."""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ofx.runner.context import context_copy
from ofx.runner.executors import Executor
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.profile_env import (
    build_profile_env_overrides,
    build_profile_var_overrides,
)
from ofx.settings import settings
from ofx.utils.file_cleanup import remove_tree
from ofx.utils.workflow_utils import workflow_dirs_with_path

logger = logging.getLogger(settings.app_branding)

_INPUT_TYPE_MAP: dict[str, type[Any] | tuple[type[Any], ...]] = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}

class WorkflowExecutor(Executor):
    @staticmethod
    def _activate_time_window(
        runner,
        window: Any,
        *,
        denied_message: str,
        active_message: str | None = None,
    ) -> None:
        from ofx.profiles.time_window import TimeWindowGuard, check_time_window

        result = check_time_window(window)
        if not result["allowed"]:
            raise RuntimeError(
                f"Workflow aborted: {result['message']}. {denied_message}"
            )
        if result["message"]:
            runner._log_warning(result["message"])
        runner._time_guard = TimeWindowGuard(
            window=window,
            on_warn=runner._log_warning,
            on_abort=lambda msg: runner._log_error(
                f"🛑 {msg} - workflow will be aborted"
            ),
        )
        runner._time_guard.start()
        if active_message:
            runner._log_info(active_message)

    async def pre_run(self, runner) -> None:
        await runner._resolve_template_fields(["name", "description", "tags", "env", "defaults"])
        runner._log_debug(
            f"Resolved workflow: {runner.model.model_dump(exclude={'jobs'})}"
        )

        # Set up run directory — use project runs/ dir if active, otherwise temp
        output_path = runner.ctx.output_path
        if output_path:
            output_path.mkdir(parents=True, exist_ok=True)

        try:
            from ofx.commands.project.project_manager import ProjectManager
            wf_name = runner.model.name or "workflow"
            project_run_dir = ProjectManager.get_run_dir(wf_name)
            if project_run_dir is not None:
                runner._run_dir = project_run_dir
            else:
                runner._run_dir = Path(tempfile.mkdtemp(prefix="ofx_run_"))
        except Exception:
            runner._run_dir = Path(tempfile.mkdtemp(prefix="ofx_run_"))

        # Create organized subdirectories
        runner._run_dir.mkdir(parents=True, exist_ok=True)
        (runner._run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (runner._run_dir / "logs").mkdir(parents=True, exist_ok=True)

        # Set output_path to run dir only if not explicitly set by caller
        if runner.ctx.output_path is None:
            runner.ctx.output_path = runner._run_dir

        runner.update_env({"OFX_RUN_DIR": str(runner._run_dir)})
        logger.debug("Run directory: %s", runner._run_dir)
        runner.update_vars(
            {"working_directory": runner.model.defaults.run.working_directory}
        )
        runner.update_context(workflow_dir=runner.model.workflow_path.parent)
        runner._log_debug(f"Workflow Dispatch: {runner.model.dispatch}")
        dispatch = runner.model.dispatch
        runner._log_debug(f"Workflow Call: {runner.model.call}")
        call = runner.model.call

        if dispatch and not runner._is_reused:
            runner.update_inputs(
                await self.process_inputs(
                    runner,
                    runner.ctx.inputs,
                    dispatch.inputs,
                )
            )

        if call and runner._is_reused:
            runner.update_inputs(
                await self.process_inputs(
                    runner,
                    runner.ctx.inputs,
                    call.inputs,
                )
            )
            runner.update_secrets(
                await self.process_inputs(
                    runner,
                    runner.ctx.secrets,
                    call.secrets,
                )
            )
            from ofx.utils.log import register_secrets

            register_secrets(runner.ctx.secrets)

        self.expand_list_inputs_to_matrix(runner)
        runner.update_context(
            workflow_dirs=workflow_dirs_with_path(
                runner.ctx.workflow_dirs,
                runner.model.defaults.workflows_base_dir.absolute(),
            )
        )
        runner._log_debug(f"Processed context: {runner.ctx}")
        runner.update_env(runner.model.env)
        await self.apply_profile(runner)
        self.apply_cli_time_window(runner)
        await runner.reg_set(
            RunnerRegistryKeys.MODEL,
            runner.model.model_dump(exclude={"jobs", "env"}),
        )
        tools = getattr(runner.model, "tools", None)
        if tools:
            from ofx.runner.tool_installer import ToolInstallerRunner

            installer = ToolInstallerRunner(
                tools=tools,
                ctx=context_copy(runner.ctx),
                parent=runner,
                show_console=False,
            )
            await installer.run()

    async def do_run(self, runner) -> None:
        await self.plan_jobs(runner)
        from ofx.runner.workflow_execution import WorkflowExecutionManager
        from ofx.runner.runner import Runner
        from ofx.runner.error_helpers import extract_root_error

        result = await WorkflowExecutionManager(runner).run(
            runner._schedule,
            runner._staged_jobs,
        )
        if result.failed_job_ids:
            for job_runner in runner._runners.values():
                if not isinstance(job_runner, Runner):
                    continue
                try:
                    await job_runner._post_run()
                except Exception as exc:
                    runner._log_debug(
                        f"post_run cleanup failed for {job_runner.model.jid}: {exc}"
                    )
            await self.store_summaries(runner)

            lines: list[str] = []
            for job_id in result.failed_job_ids:
                job_runner = runner._runners.get(job_id)
                error = job_runner._error if job_runner else None
                lines.append(f"job '{job_id}': {extract_root_error(error)}")

            message = "Job failure(s):\n" + "\n".join(lines)
            await runner.reg_set(
                RunnerRegistryKeys.ERRORS,
                {
                    "message": message,
                    "failed_jobs": result.failed_job_ids,
                    "failed_stages": result.failed_stage_indices,
                },
            )
            raise RuntimeError(message)

    async def post_run(self, runner) -> None:
        if runner._time_guard:
            runner._time_guard.stop()
        if runner._is_reused:
            failed_job_ids = [
                job_runner.model.jid
                for job_runner in runner._runners.values()
                if job_runner.is_failed
            ]
            if failed_job_ids:
                raise RuntimeError(
                    f"Reusable workflow '{runner.model.name}': "
                    f"{len(failed_job_ids)}/{len(runner._runners)} "
                    f"job(s) failed ({', '.join(failed_job_ids)}). "
                    "Cannot retrieve outputs."
                )

            call = runner.model.call
            output_templates = call.outputs if call and call.outputs else {}
            if output_templates:
                outputs = {
                    key: await runner._resolve_template(value)
                    for key, value in output_templates.items()
                }
                await runner.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)
        await self.store_summaries(runner)
        runner._log_debug(f"result: {await runner.get_result()}")

        # Write summary.json to run directory
        await self._write_run_summary(runner)

        # Only clean up temp directories, not project run directories
        if not str(runner._run_dir).startswith(str(Path.home() / ".ofx" / "projects")):
            remove_tree(
                runner._run_dir,
                on_error=lambda message: logger.debug(message),
                label="run dir",
            )

    async def on_failure(self, runner) -> None:
        # Write summary even on failure
        await self._write_run_summary(runner)

        if not str(runner._run_dir).startswith(str(Path.home() / ".ofx" / "projects")):
            remove_tree(
                runner._run_dir,
                on_error=lambda message: logger.debug(message),
                label="run dir",
            )

    async def _write_run_summary(self, runner) -> None:
        """Write a summary.json to the run directory and expose run_dir."""
        run_dir = getattr(runner, "_run_dir", None)
        if run_dir is None or not run_dir.exists():
            return
        try:
            result = await runner.get_result()
            status = getattr(result, "status", None)
            status_str = status.value if hasattr(status, "value") else str(status)
            error = getattr(result, "error", None)
            outputs = getattr(result, "outputs", {}) or {}
            summary = {
                "workflow": runner.model.name,
                "status": status_str,
                "error": error,
                "outputs": outputs,
                "run_dir": str(run_dir),
            }
            summary_path = run_dir / "summary.json"
            summary_path.write_text(json.dumps(summary, indent=2, default=str))
            runner._log_debug(f"Summary written to {summary_path}")

            await runner.reg_set(
                RunnerRegistryKeys.OUTPUTS,
                {**outputs, "run_dir": str(run_dir)},
            )
        except Exception as e:
            logger.debug("Failed to write run summary: %s", e)

    async def process_inputs(
        self,
        runner,
        req_inputs: dict,
        input_blueprint: dict,
    ) -> dict[str, Any]:
        runner._log_debug(
            f"Processing inputs: {req_inputs} with blueprint: {input_blueprint}"
        )

        req_inputs = dict(req_inputs)
        for key, constraint in input_blueprint.items():
            alias_candidates = (
                [constraint.alias]
                if isinstance(constraint.alias, str)
                else list(constraint.alias or [])
            )
            alias = next(
                (candidate for candidate in alias_candidates if candidate in req_inputs),
                None,
            )

            if key in req_inputs:
                if alias is not None:
                    runner._log_warning(
                        f"Both input '{key}' and its alias '{alias}' are provided. "
                        f"Using value from '{key}' and ignoring alias."
                    )
                    req_inputs.pop(alias)
                value = req_inputs[key]
            elif alias is not None:
                value = req_inputs[alias]
            else:
                if constraint.required:
                    raise ValueError(
                        f"Input '{key}' is required but not provided in the inputs."
                    )
                req_inputs[key] = constraint.default
                continue

            if constraint.type == "string" and isinstance(value, list):
                req_inputs[key] = value
                continue

            expected_type = _INPUT_TYPE_MAP.get(constraint.type)
            if expected_type is None:
                raise ValueError(
                    f"Unsupported input type '{constraint.type}'. "
                    f"Supported types are: {', '.join(_INPUT_TYPE_MAP.keys())}."
                )
            if not isinstance(value, expected_type):
                raise ValueError(
                    f"Input '{key}' has invalid type: {type(value).__name__}. "
                    f"Expected type: {constraint.type}."
                )
            req_inputs[key] = value
        return {
            key: await runner._resolve_template(value)
            for key, value in req_inputs.items()
        }

    def expand_list_inputs_to_matrix(self, runner) -> None:
        if not (runner.model.dispatch and not runner._is_reused):
            return

        from ofx.models.strategy import MatrixStrategy

        matrix_inputs: dict[str, list[Any]] = {}
        for key, constraint in runner.model.dispatch.inputs.items():
            value = runner.ctx.inputs.get(key)
            if isinstance(value, list) and constraint.type == "string":
                matrix_inputs[key] = value

        if not matrix_inputs:
            return

        for key, values in matrix_inputs.items():
            runner._log_info(
                f"Auto-expanding input '{key}' ({len(values)} values) as matrix"
            )
            needle = f"inputs.{key}"
            for job in runner.model.jobs.values():
                references_input = False
                for step in job.steps:
                    fields = [step.run, step.script, step.script_file]
                    if step.run_with:
                        fields.extend(step.run_with.values())
                    if any(field and needle in str(field) for field in fields):
                        references_input = True
                        break
                if not references_input:
                    continue

                if not job.strategy:
                    job.strategy = MatrixStrategy.model_validate(
                        {"matrix": {key: values}}
                    )
                elif key not in job.strategy.matrix:
                    job.strategy.matrix[key] = values

        runner.update_vars({"_matrix_input_keys": list(matrix_inputs)})
        runner.update_context(
            inputs={
                key: value
                for key, value in runner.ctx.inputs.items()
                if key not in matrix_inputs
            }
        )

    async def apply_profile(self, runner) -> None:
        profile_name = runner.ctx.vars.get("_cli_profile_name") or runner.model.defaults.profile or ""
        if not profile_name:
            return

        from ofx.profiles.manager import get_profile_manager

        profile = get_profile_manager().resolve_or_default(profile_name)
        if profile is None:
            return
        runner._profile = profile
        runner._log_info(f"Applying profile: {profile_name}")
        runner.update_env_and_vars(
            build_profile_env_overrides(profile),
            build_profile_var_overrides(profile),
        )

        if not profile.time_window.enabled:
            return

        time_window = profile.time_window
        self._activate_time_window(
            runner,
            time_window,
            denied_message=(
                f"Profile '{profile_name}' restricts execution to "
                f"{time_window.start}–{time_window.end} "
                f"on {', '.join(day.title() for day in time_window.days)} "
                f"({time_window.timezone})."
            ),
        )

    def apply_cli_time_window(self, runner) -> None:
        if runner._time_guard or runner._is_reused:
            return

        tw_str = runner.ctx.vars.get("_cli_time_window", "")
        if not tw_str or "-" not in tw_str:
            return

        from ofx.profiles.models import TimeWindow

        start, end = (part.strip() for part in tw_str.split("-", 1))
        window = TimeWindow(
            enabled=True,
            start=start,
            end=end,
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

    async def plan_jobs(self, runner) -> None:
        from ofx.runner.workflow_scheduler import WorkflowScheduler

        schedule = WorkflowScheduler(runner.model.jobs).plan()
        runner._staged_jobs = schedule.staged_jobs
        runner._schedule = schedule.schedule
        runner._log_debug(f"Stages: {runner._schedule}")

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

        summary_payload = summary.to_dict()
        await runner.reg_set(RunnerRegistryKeys.SUMMARY, summary_payload)
        await runner.reg_set(RunnerRegistryKeys.SUMMARY_UNIFIED, unified)

        outputs = dict(await runner.reg_get(RunnerRegistryKeys.OUTPUTS) or {})
        outputs["__summary__"] = unified
        await runner.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)
        project_path = runner.ctx.vars.get("project_path") or ""
        if not project_path:
            return

        try:
            from ofx.runner.findings_export import (
                collect_typed_outputs,
                export_typed_outputs,
            )

            all_typed = await collect_typed_outputs(runner._runners)
            if not all_typed:
                return

            summaries = export_typed_outputs(project_path, all_typed)
            if summaries:
                runner._log_info("Findings exported to project:")
                for summary_line in summaries:
                    runner._log_info(summary_line)
                outputs["__findings_export__"] = summaries
                await runner.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)
        except Exception as exc:
            runner._log_debug(f"Findings export failed: {exc}")
