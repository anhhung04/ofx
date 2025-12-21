"""
All runner implementations in one file to avoid circular imports.
"""
import asyncio
import logging
import os
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Any, Dict

from ofx.models.step import Step
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.base import BaseRunner, RunContext, RunnerStatus, RunResult
from ofx.runner.core.hooks import HookHandler, HookPoint, HookContext
from ofx.runner.core.scheduler import JobScheduler
from ofx.runner.core.progress import ProgressTracker
from ofx.runner.loaders.workflow_loader import WorkflowLoader
from ofx.runner.registry.job_registry import JobRegistry
from ofx.runner.executors.command import CommandExecutor, ScriptExecutor
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)
processor = ThreadPoolExecutor(max_workers=(settings.workers * 2))
DEFAULT_SHELL = "/bin/bash"


class RunType(Enum):
    SCRIPT = "script"
    COMMAND = "command"
    WORKFLOW = "workflow"


class WorkflowRunner(BaseRunner):
    def __init__(
        self,
        workflow: Workflow,
        ctx: RunContext,
        parent: BaseRunner | None = None,
    ):
        super().__init__(workflow, ctx, parent)
        self._model = workflow
        self._is_reused = self._parent is not None
        self._processor = processor
        self._scheduler = JobScheduler(workflow)
        self._registry = JobRegistry()
        self._progress_tracker = ProgressTracker(is_reused=self._is_reused)
        self._schedule = []
        self._total_steps = 0
        self._completed_steps = 0

    async def _do_run(self):
        with self._progress_tracker.create_workflow_progress(
            self.model.name, self._total_steps
        ) as progress:
            for idx, stage in enumerate(self._schedule):
                logger.debug(self._produce_log(f"Running stage {idx + 1}: {stage}"))
                futures = {
                    self._processor.submit(self._run_job, job_id): job_id
                    for job_id in stage
                }
                completed_jobs = set()
                while len(completed_jobs) < len(stage):
                    done, _ = wait(
                        [f for f in futures.keys() if futures[f] not in completed_jobs],
                        timeout=0.1,
                        return_when=FIRST_COMPLETED,
                    )
                    for f in done:
                        job_id = futures[f]
                        if job_id not in completed_jobs:
                            try:
                                result = f.result()
                                if not result:
                                    raise RuntimeError(
                                        f"Failed when polling job '{job_id}'"
                                    )
                                logger.debug(
                                    self._produce_log(f"Job '{job_id}' completed")
                                )
                            except Exception as e:
                                raise RuntimeError(
                                    self._produce_log(
                                        f"Failed when polling job '{job_id}': {e}"
                                    )
                                )
                            finally:
                                completed_jobs.add(job_id)

                    current_steps_completed = sum(
                        self._registry.get_job_runner(jid).processed_steps
                        for jid in stage
                    )
                    self._completed_steps = max(
                        self._completed_steps, current_steps_completed
                    )
                    self._progress_tracker.update_workflow_progress(
                        self.model.name,
                        idx + 1,
                        len(self._schedule),
                        min(self._completed_steps, self._total_steps),
                        self._total_steps,
                    )

            self._progress_tracker.complete_workflow_progress(
                self.model.name, self._total_steps
            )

    def _planning_jobs(self) -> int:
        self._schedule, self._total_steps = self._scheduler.plan_execution()
        self._completed_steps = 0
        return self._total_steps

    def _run_job(self, job_id: str) -> bool:
        job = self.model.jobs[job_id]
        logger.debug(self._produce_log(f"starting job: {job}"))
        job_data = self._resolve_template(
            job.model_dump(exclude={"outputs", "steps"})
        )
        self._registry.register_job(job_id, job_data)
        self._ctx.vars.update({"jobs": self._registry.get_all_jobs()})
        job_runner = JobRunner(
            job,
            self.ctx_vars,
            parent=self,
        )
        self._registry.set_job_runner(job_id, job_runner)
        try:
            self._run_and_monitor_job(job)
            job_result = job_runner.get_result()
            self._registry.update_job(job_id, job_result.model_dump())
            job = self._registry.get_job(job_id)
            if not job:
                raise RuntimeError(f"Job '{job_id}' not found in registry after run.")
            job["steps"] = {}
            job["steps"].update(job_result.outputs.get("steps", {}))
            self._ctx.vars.update({"jobs": self._registry.get_all_jobs()})
            return True
        except Exception as e:
            logger.error(job_runner._produce_log(f"Job execution failed: {e}"))
            return False

    def _run_and_monitor_job(self, job: Job):
        job_id = job.jid
        job_runner = self._registry.get_job_runner(job_id)
        if not job_runner:
            raise ValueError(f"Job with ID '{job_id}' not found.")
        job_name = job.name or job_id
        total_steps = job_runner.total_steps

        self._progress_tracker.run_job_with_progress(
            job_id, job_name, total_steps, job_runner, self._processor
        )

    async def _pre_run(self):
        # Register and execute hooks using base class helpers
        self._register_hooks_from_model()
        await self._execute_pre_run_hooks()
        
        if not self.ctx_vars.output_path.exists():
            self.ctx_vars.output_path.mkdir(parents=True, exist_ok=True)
        
        # Change to workflow working directory
        if self.model.defaults:
            os.chdir(self.model.defaults.run.working_directory)
            workflows_base_dir = Path(
                self._resolve_template(self.model.defaults.workflows_base_dir)
            )
            WorkflowLoader.add_workflow_dir(workflows_base_dir.absolute())
        
        logger.debug(
            self._produce_log(f"Workflow Dispatch: {self.model.workflow_dispatch}")
        )
        logger.debug(self._produce_log(f"Workflow Call: {self.model.workflow_call}"))
        if self.model.workflow_dispatch and not self._is_reused:
            self._ctx.inputs.update(
                self._process_inputs(
                    self._ctx.inputs, self.model.workflow_dispatch.inputs
                )
            )
        if self.model.workflow_call and self._is_reused:
            self._ctx.inputs.update(
                self._process_inputs(self._ctx.inputs, self.model.workflow_call.inputs)
            )
            self._ctx.secrets.update(
                self._process_inputs(
                    self._ctx.secrets, self.model.workflow_call.secrets
                )
            )

        self._resolve_template_fields(
            ["name", "tools", "env", "description", "tags", "schedule"]
        )
        for job_id, job in self.model.jobs.items():
            self._model.jobs[job_id].name = self._resolve_template(job.name)

        logger.debug(self._produce_log(f"Resolved workflow: {self.model.model_dump()}"))

        self._ctx.envs.update(self.model.env)
        logger.debug(self._produce_log(f"Processed context: {self.ctx_vars}"))
        await self._install_tools()
        self._planning_jobs()

    async def _post_run(self):
        # Execute post_run hooks using base class helper
        await self._execute_post_run_hooks()
        
        if self._status != RunnerStatus.COMPLETED and self._error:
            logger.error(self._produce_log(f"error: {self._error}"))
        self._result.outputs.update(self._registry.get_all_jobs())
        if self._is_reused and self.model.workflow_call:
            if not self.is_success:
                raise RuntimeError(
                    self._produce_log(
                        f"Reusable workflow '{self.model.name}' failed. Cannot retrieve outputs."
                    )
                )
            self._result.outputs = {
                k: self._resolve_template(v)
                for k, v in self.model.workflow_call.outputs.items()
            }
        logger.debug(
            self._produce_log(
                f"job execution status: {[(job['name'], job['status']) for job in self._registry.get_all_jobs().values()]}"
            )
        )
        self._status = (
            self._status
            if not self._is_reused
            else (
                RunnerStatus.COMPLETED
                if all(
                    [
                        job["status"] == RunnerStatus.COMPLETED
                        for job in self._registry.get_all_jobs().values()
                    ]
                )
                else RunnerStatus.FAILED
            )
        )
        if (
            self.ctx_vars.output_path.exists()
            and len(os.listdir(self.ctx_vars.output_path.absolute())) == 0
        ):
            os.rmdir(self.ctx_vars.output_path)
        logger.debug(self._produce_log(f"result: {self.get_result()}"))
        if not self._is_reused:
            self._processor.shutdown(wait=True)

    async def _install_tools(self):
        tools = self.model.tools
        if not tools:
            return
        for tool_bin, install_cmd in tools.items():
            if not shutil.which(tool_bin):
                logger.warning(
                    self._produce_log(
                        f"Installing tool '{tool_bin}' with command: {install_cmd}"
                    )
                )
                executor = CommandExecutor(
                    install_cmd,
                    RunContext(envs=self.ctx_vars.envs),
                    self,
                )
                result = await executor.execute()
                if result.get("exit_code", 0) != 0:
                    raise RuntimeError(f"Failed to install tool '{tool_bin}'")
            else:
                logger.debug(
                    self._produce_log(f"Tool '{tool_bin}' is already installed")
                )

    def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> Dict[str, Any]:
        logger.debug(
            self._produce_log(
                f"Processing inputs: {req_inputs} with blueprint: {input_blueprint}"
            )
        )

        for key, contrain in input_blueprint.items():
            if key not in req_inputs and contrain.required:
                raise ValueError(
                    f"Input '{key}' is required but not provided in the inputs."
                )
            if key in req_inputs:
                value = req_inputs[key]
                if not self._check_input_type(value, contrain.type):
                    raise ValueError(
                        f"Input '{key}' has invalid type: {type(value).__name__}. "
                        f"Expected type: {contrain.type}."
                    )
            else:
                req_inputs[key] = contrain.default
        for key, value in req_inputs.items():
            req_inputs[key] = self._resolve_template(value)
        
        return req_inputs

    def _check_input_type(self, value: Any, input_type: str) -> bool:
        if input_type == "string":
            return isinstance(value, str)
        elif input_type == "number":
            return isinstance(value, (int, float))
        elif input_type == "boolean":
            return isinstance(value, bool)
        elif input_type == "array":
            return isinstance(value, list)
        elif input_type == "object":
            return isinstance(value, dict)

        raise ValueError(
            f"Unsupported input type '{input_type}' for value '{value}'. "
            f"Supported types are: string, number, boolean, array, object."
        )

    def _produce_log(self, message: Any) -> str:
        workflow_name = self.model.name
        if self._is_reused:
            if self.parent:
                return self.parent._produce_log(f"[['{workflow_name}']] -> {message}")
        return f"['{workflow_name}'] -> {message}"

    def get_output_path(self) -> Path:
        return self.ctx_vars.output_path

    @staticmethod
    def find_flow(workflow_name: str) -> Workflow:
        return WorkflowLoader.find_flow(workflow_name)

    def get_job_status(self, job_id: str) -> RunnerStatus:
        status = self._registry.get_job_status(job_id)
        if not status:
            raise ValueError(f"Job with ID '{job_id}' not found.")
        return status
    
    def get_job_from_registry(self, job_id: str) -> Dict[str, Any] | None:
        return self._registry.get_job(job_id)

    @property
    def model(self) -> Workflow:
        return self._model


class JobRunner(BaseRunner):
    def __init__(self, job: Job, ctx: RunContext, parent: WorkflowRunner | None = None):
        super().__init__(job, ctx, parent)
        self._model = job
        self._step_registry: Dict[str, Any] = {}
        self._processed_steps = 0

    async def _do_run(self):
        for idx, step in enumerate(self.model.steps):
            # Execute on_iter_step hook
            hook_ctx = HookContext(
                model=self.model,
                step_index=idx,
                inputs=self.ctx_vars.inputs,
                runner=self,
            )
            await self._hook_handler.execute_hooks(HookPoint.ON_ITER_STEP, hook_ctx)
            
            step_runner = StepRunner(
                step,
                RunContext(
                    inputs={
                        **self.ctx_vars.inputs,
                        **self._resolve_template(step.run_with),
                    },
                    envs={**self.ctx_vars.envs, **self._resolve_template(step.env)},
                    output_path=self.ctx_vars.output_path,
                    secrets={
                        **self.ctx_vars.secrets,
                        **self._resolve_template(
                            step.secrets if step.secrets != "inherit" else {}
                        ),
                    },
                    vars=self.ctx_vars.vars,
                ),
                self,
            )
            start_time = time.time()
            result = await step_runner.run()
            result.metadata.update({"duration": int(time.time() - start_time)})
            step_name = step.name
            step_id = step.step_index
            dump_model = result.model_dump()
            
            # Register step result with multiple access patterns
            self._step_registry[step_id] = dump_model  # Numeric index
            self._step_registry[str(step_id)] = dump_model  # String index for template compatibility
            if step.id:
                self._step_registry[step.id] = dump_model  # Named ID if provided
            
            self._processed_steps += 1
            if not step_runner.is_success and not step.continue_on_error:
                self._status = RunnerStatus.FAILED
                self._error = result.error
                raise RuntimeError(
                    self._produce_log(
                        f"(step '{step_name}') -> job execution stopped due to step failure:\n {self._error}"
                    )
                )

    async def _pre_run(self):
        # Register and execute hooks using base class helpers
        self._register_hooks_from_model()
        await self._execute_pre_run_hooks()
        
        self._resolve_template_fields(["name", "needs", "run_if", "env"])
        for idx, step in enumerate(self._model.steps):
            self._model.steps[idx].name = self._resolve_template(step.name)
            self._model.steps[idx].id = self._resolve_template(step.id)
        self._ctx.envs.update(self.model.env)
        logger.debug(self._produce_log(f"Resolved job: {self.model.model_dump()}"))
        if self.model.needs:
            unmet_deps = []
            for job_id in self.model.needs:
                try:
                    if self.parent.get_job_status(job_id) != RunnerStatus.COMPLETED:
                        unmet_deps.append(job_id)
                except Exception as e:
                    logger.error(
                        self._produce_log(
                            f"Error checking dependency status for {job_id}: {e}"
                        )
                    )
                    unmet_deps.append(job_id)

            if len(unmet_deps) > 0:
                raise RuntimeError(
                    f"Job cannot run because dependencies are not met: {unmet_deps}"
                )

        if not eval(str(self._model.run_if)):
            raise RuntimeError(self._produce_log(f"Job condition is not met"))
        self._ctx.vars.update(
            {
                "steps": self._step_registry,
                "needs": {
                    jid: self.parent.get_job_from_registry(jid)
                    for jid in self.model.needs
                },
            }
        )

    async def _post_run(self):
        # Execute post_run hooks using base class helper
        await self._execute_post_run_hooks()
        
        if self.status != RunnerStatus.COMPLETED or self._error:
            logger.error(self._produce_log(f"job failed: {self._error}"))
        self._ctx.vars.update({"steps": self._step_registry})
        self._result.outputs.update({"steps": self._step_registry})
        if self.model.outputs:
            for key, value in self.model.outputs.items():
                self._result.outputs[key] = self._resolve_template(value)
        logger.debug(
            self._produce_log(
                f"job '{self.model.name or self.model.jid}' result: {self._result}"
            )
        )

    def _produce_log(self, message: Any) -> str:
        job_name = self._model.name or self._model.jid
        msg = f"('{job_name}') -> {message}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def processed_steps(self) -> int:
        return self._processed_steps

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)

    @property
    def model(self) -> Job:
        return self._model

    @property
    def parent(self) -> WorkflowRunner:
        if not self._parent:
            raise ValueError("orphan JobRunner detected - parent WorkflowRunner is None")
        assert isinstance(self._parent, WorkflowRunner)
        return self._parent


class StepRunner(BaseRunner):
    def __init__(
        self, step: Step, context: RunContext, parent: JobRunner | None = None
    ):
        super().__init__(step, context, parent)
        self._model = step

    async def _pre_run(self):
        # Register and execute hooks using base class helpers
        self._register_hooks_from_model()
        await self._execute_pre_run_hooks()
        
        self._run_type = self._parse_run_type()
        self._resolve_template_fields(
            [
                "run",
                "run_if",
                "run_with",
                "uses",
                "script",
                "shell",
                "log_stdout",
                "working_directory",
            ]
        )

        self._result.metadata.update({"step": self._model})

        if not bool(eval(str(self._model.run_if))):
            self._status = RunnerStatus.CANCELED
            raise Exception("Step skipped due to run_if condition")

    async def _post_run(self):
        # Execute post_run hooks using base class helper
        await self._execute_post_run_hooks()
        
        # Handle stdout output
        self._handle_stdout_output()
        logger.debug(self._produce_log(f"result: {self._result}"))
    
    def _handle_stdout_output(self):
        """Handle stdout output - log or save to file."""
        stdout = self._result.outputs.get("stdout", "")
        if self.model.log_stdout:
            logger.info(self._produce_log(f"stdout:\n{stdout}\n"))
        else:
            tmp_file = (
                self.ctx_vars.output_path
                / f"stdout_{str(self.parent.model.name).replace(' ','_')}_{str(self.model.name).replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            )
            logger.info(f"Saving output to {tmp_file}")
            tmp_file.write_text(stdout)

    def _get_job_defaults(self):
        """Safely get job defaults from parent."""
        if self.parent and isinstance(self.parent, JobRunner):
            return self.parent.model.defaults
        return None

    def _get_workflow_defaults(self):
        """Safely get workflow defaults from grandparent."""
        if self.parent and self.parent.parent and isinstance(self.parent.parent, WorkflowRunner):
            return self.parent.parent.model.defaults
        return None

    async def _do_run(self):
        if self._run_type is RunType.WORKFLOW:
            await self._execute_workflow()
        elif self._run_type is RunType.SCRIPT:
            await self._execute_script()
        elif self._run_type is RunType.COMMAND:
            await self._execute_command()
    
    async def _execute_workflow(self):
        """Execute a nested workflow step."""
        output_path = self.ctx_vars.output_path
        if self.parent and self.parent.parent:
            output_path = self.parent.parent.ctx_vars.output_path
        
        runner = WorkflowRunner(
            WorkflowLoader.find_flow(self._model.uses or ""),
            RunContext(
                inputs=self._resolve_template(self._model.run_with),
                envs=self.ctx_vars.envs,
                output_path=output_path,
                secrets=(
                    self.ctx_vars.secrets
                    if self.model.secrets == "inherit"
                    else self._resolve_template(self.model.secrets)
                ),
            ),
            parent=self,
        )
        
        res = await runner.run()
        self._status = res.status
        self._error = res.error
        for k, v in res.model_dump().items():
            setattr(self._result, k, v)
        logger.debug(self._produce_log(f"result: {self.get_result()}"))
    
    async def _execute_script(self):
        """Execute a Python script step."""
        assert self.model.script is not None, "Script cannot be None for SCRIPT run type"
        
        # Execute before_step hook with auto-resolved fields
        hook_ctx = HookContext(
            model=self.model,
            script=self.model.script,
            run=self.model.script,
            inputs=self._ctx.inputs,
            runner=self,
        )
        hook_ctx = await self._hook_handler.execute_hooks(HookPoint.BEFORE_STEP, hook_ctx)
        
        # Execute script
        shell = self.model.get_shell(self._get_job_defaults(), self._get_workflow_defaults())
        executor = ScriptExecutor(
            self.model.script,
            self.ctx_vars.model_copy(),
            self,
            shell=shell,
            working_dir=self._resolve_working_dir(),
            timeout_minutes=self.model.timeout,
        )
        result_data = await executor.execute()
        self._result.outputs.update(result_data)
        
        # Execute after_step hook
        hook_ctx.outputs = result_data
        hook_ctx = await self._hook_handler.execute_hooks(HookPoint.AFTER_STEP, hook_ctx)
        self._result.outputs.update(hook_ctx.outputs)
    
    async def _execute_command(self):
        """Execute a shell command step."""
        assert self.model.run is not None, "Run cannot be None for COMMAND run type"
        
        # Execute before_step hook with auto-resolved fields
        hook_ctx = HookContext(
            model=self.model,
            command=self.model.run,
            run=self.model.run,
            inputs=self._ctx.inputs,
            runner=self,
        )
        hook_ctx = await self._hook_handler.execute_hooks(HookPoint.BEFORE_STEP, hook_ctx)
        
        # Execute command
        shell = self.model.get_shell(self._get_job_defaults(), self._get_workflow_defaults())
        executor = CommandExecutor(
            self.model.run,
            self.ctx_vars.model_copy(),
            self,
            shell=shell,
            working_dir=self._resolve_working_dir(),
            timeout_minutes=self.model.timeout,
        )
        result_data = await executor.execute()
        self._result.outputs.update(result_data)
        
        # Execute after_step hook
        hook_ctx.outputs = result_data
        hook_ctx = await self._hook_handler.execute_hooks(HookPoint.AFTER_STEP, hook_ctx)
        self._result.outputs.update(hook_ctx.outputs)

    def _produce_log(self, message: Any) -> str:
        step_index = self._model.step_index
        msg = f"{{'{step_index}'}} -> {message}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _parse_run_type(self) -> RunType:
        step = self._model
        step_name = step.name
        if step.script:
            return RunType.SCRIPT
        elif step.run:
            return RunType.COMMAND
        elif step.uses:
            return RunType.WORKFLOW
        else:
            raise ValueError(
                self._produce_log(
                    f"Step '{step_name}' does not define a valid run type. "
                    "Step must include one of: 'script', 'run', or 'uses'."
                )
            )

    def _resolve_working_dir(self) -> Path:
        """Resolve working directory using model method."""
        return self._model.get_working_directory(self._get_job_defaults(), self._get_workflow_defaults())

    @property
    def model(self) -> Step:
        return self._model

    @property
    def parent(self) -> JobRunner:
        if not self._parent:
            raise ValueError("orphan StepRunner detected - parent JobRunner is None")
        assert isinstance(self._parent, JobRunner)
        return self._parent
