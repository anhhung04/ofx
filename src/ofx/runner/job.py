import os
import subprocess
import base64
import re
import sys
import tempfile
import logging
import time
import shlex
from ofx.runner.base import BaseRunner, RunnerStatus, RunContext
from ofx.models.job import Job
from ofx.models.step import Step

from enum import Enum
from pathlib import Path
from zlib import compress
from typing import Dict, Any

logger = logging.getLogger("ofx")


class RunType(Enum):
    SCRIPT = "script"
    COMMAND = "command"
    WORKFLOW = "workflow"


class JobRunner(BaseRunner):
    """
    Runner for executing a job consisting of multiple steps.

    This class handles the execution of job steps, including command execution,
    script running, and sub-workflow invocation.
    """

    def __init__(self, job_id: str, job: Job, ctx: RunContext):
        super().__init__(job.name, ctx)
        self._job = job
        self._job_id = job_id
        self._processed_steps = 0
        self._step_outputs = []
        self._registered_steps_outputs = {}

    async def _do_run(self):
        """
        Execute all steps in the job sequentially.

        This method processes each step in the job, updates the step outputs,
        and handles failures based on continue_on_error settings.

        Raises:
            RuntimeError: If a step fails and continue_on_error is False
        """
        try:
            async for step_output in self._process_steps():
                step_name = step_output["step"].name
                step_id = step_output["index"]
                logger.debug(
                    self._produce_log(
                        f"(step '{step_name}') -> completed with status: {step_output['status'].value}"
                    )
                )
                self._step_outputs.insert(step_id, step_output)
                self._processed_steps += 1
                if (
                    step_output["status"] == RunnerStatus.FAILED
                    and not step_output["step"].continue_on_error
                ):
                    self._status = RunnerStatus.FAILED
                    self._error = step_output.get("error", "Unknown error")
                    raise RuntimeError(
                        self._produce_log(
                            f"(step '{step_name}') -> job execution stopped due to step failure: {self._error}"
                        )
                    )
        except Exception as e:
            if not isinstance(e, RuntimeError):
                logger.error(
                    self._produce_log(
                        f"Unexpected error during job execution: {str(e)}"
                    )
                )
            raise

    async def _pre_run(self):
        """
        Perform pre-run validation and setup.

        Verifies that all dependencies (jobs specified in "needs") have completed
        successfully before allowing this job to run.

        Raises:
            RuntimeError: If any job dependencies are not met
        """
        if not hasattr(self, "_context_provider"):
            raise RuntimeError(
                self._produce_log("No context provider attached to the runner")
            )

        if self._job.needs:
            # Check if all dependency jobs have completed successfully
            unmet_deps = []
            for job_id in self._job.needs:
                try:
                    status = self._context_provider.get_job_status(job_id)
                    if status != RunnerStatus.COMPLETED:
                        unmet_deps.append(job_id)
                except Exception as e:
                    logger.error(
                        self._produce_log(
                            f"Error checking dependency status for {job_id}: {e}"
                        )
                    )
                    unmet_deps.append(job_id)

            if unmet_deps:
                raise RuntimeError(
                    f"Job cannot run because dependencies are not met: {unmet_deps}"
                )

            logger.debug(
                self._produce_log(f"All dependencies satisfied: {self._job.needs}")
            )

        if self._job.run_if:
            raw_cond = str(self._job.run_if)
            self._job.run_if = self._context_provider.resolve_template(self._job.run_if)
            logger.debug(
                self._produce_log(
                    f"Resolved run_if condition: '{str(self._job.run_if)}' from raw condition: '{raw_cond}'"
                )
            )
            if not eval(str(self._job.run_if)):
                raise RuntimeError(
                    self._produce_log(
                        f"Job cannot run because condition '{raw_cond}' is not met"
                    )
                )
        logger.debug(self._produce_log("Pre-run validation completed successfully"))

    async def _post_run(self):
        """
        Perform post-run tasks and prepare the final result.

        This method collects job execution results and prepares the final output
        for retrieval by the workflow manager.
        """
        if not self._success:
            logger.error(self._produce_log(f"Job failed with error: {self._error}"))
        outputs = {
            "steps": self._step_outputs,
        }
        outputs.update(
            {
                k: self._resolve_template_with_step(v)
                for k, v in self._job.outputs.items()
            }
        )
        self._status = RunnerStatus.COMPLETED if self._success else RunnerStatus.FAILED
        self._result = {
            "job_name": self._job.name,
            "job_id": self._job_id,
            "status": self._status,
            "processed_steps": self._processed_steps,
            "total_steps": len(self._job.steps),
            "outputs": outputs,
            "error": self._error,
        }

    def attach_context_provider(self, context_provider):
        """
        Attach a context provider to the job runner.

        The context provider supplies access to workflow-level context, secrets,
        and job status information.

        Args:
            context_provider: The workflow context provider
        """
        self._context_provider = context_provider

    async def _process_steps(self):
        """
        Process all steps in the job sequentially.

        This generator yields each step's execution result after processing.

        Yields:
            dict: The result of each step execution including status and outputs
        """
        for step_index, step in enumerate(self._job.steps):
            step = self._preprocess_step(step_index, step)
            step_name = step.name
            step_id = step.id
            try:
                run_type = self._parse_run_type(step)
                handler = getattr(self, f"_handle_{run_type.value}")
            except (ValueError, AttributeError) as e:
                logger.error(self._produce_log(f"Invalid step configuration: {e}"))
                yield {
                    "step": step,
                    "index": step_index,
                    "id": step_id,
                    "outputs": {},
                    "status": RunnerStatus.FAILED,
                    "run_type": None,
                    "error": f"Invalid step configuration: {str(e)}",
                }
                continue

            output = {}
            stderr = ""
            start_time = time.time()

            try:
                output = await handler(step)
                if (
                    isinstance(output, dict)
                    and "stdout" in output
                    and output["stdout"]
                    and step.log_stdout
                ):
                    stdout = output["stdout"]
                    if len(stdout) > 2000:
                        stdout = stdout[:2000] + "... [truncated]"
                    logger.info(
                        self._produce_log(f"(step '{step_name}') -> stdout:\n{stdout}")
                    )

                _success = output.get("status", True) is not False
            except Exception as e:
                stderr = str(e)
                _success = False
                logger.error(self._produce_log(f"(step '{step_name}') -> error: {e}"))

            finally:
                execution_time = time.time() - start_time
                step_status = (
                    RunnerStatus.COMPLETED if _success else RunnerStatus.FAILED
                )
                self._registered_steps_outputs[step_id] = {**step.model_dump()}
                self._registered_steps_outputs[step_id].update(
                    {
                        "outputs": output,
                        "status": step_status,
                        run_type: run_type,
                    }
                )
                yield {
                    "step": step,
                    "id": step_id,
                    "index": step_index,
                    "outputs": output,
                    "status": step_status,
                    "run_type": run_type,
                    "error": stderr,
                    "execution_time": execution_time,
                }

                logger.debug(
                    self._produce_log(
                        f"Step '{step_name}' completed in {execution_time:.2f}s with status: {_success}"
                    )
                )

    def _preprocess_step(self, step_id: int, step: Step) -> Step:
        step_name = (
            self._resolve_template_with_step(step.name)
            if step.name
            else f"step_{step_id}"
        )
        step.name = step_name
        logger.debug(self._produce_log(f"Processing step {step_id}: '{step_name}'"))
        if step_id > 0 and step.run_if:
            raw_cond = str(step.run_if)
            step.run_if = self._resolve_template_with_step(step.run_if)
            logger.debug(
                self._produce_log(
                    f"Resolved run_if condition: '{str(step.run_if)}' from raw condition: '{raw_cond}'"
                )
            )
            if not eval(str(step.run_if)):
                raise RuntimeError(
                    self._produce_log(
                        f"Step '{step_name}' cannot run because condition '{raw_cond}' is not met"
                    )
                )
        step.env = {k: self._resolve_template_with_step(v) for k, v in step.env.items()}
        step.secrets = {
            k: self._resolve_template_with_step(v) for k, v in step.secrets.items()
        }
        step.working_directory = self._resolve_template_with_step(
            step.working_directory
        )
        step.id = self._resolve_template_with_step(step.id)
        return step

    def _parse_run_type(self, step: Step) -> RunType:
        """
        Determine the run type of a step based on its configuration.

        Args:
            step: The step to analyze

        Returns:
            RunType: The determined run type (SCRIPT, COMMAND, or WORKFLOW)

        Raises:
            ValueError: If the step doesn't define a valid run type
        """
        step_name = step.name or "unnamed step"
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

    async def _handle_workflow(self, step: Step):
        """
        Execute a sub-workflow as defined in the step.

        This method sets up and runs a nested workflow, handling input processing,
        secrets inheritance, and result validation.

        Args:
            step: The step configuration

        Returns:
            Dict containing the workflow execution outputs

        Raises:
            RuntimeError: If the sub-workflow execution fails
        """
        step_name = step.name or "workflow step"
        workflow_name = self._resolve_template_with_step(step.uses)

        logger.debug(
            self._produce_log(
                f"(step '{step_name}') -> running workflow: {workflow_name} with inputs: {step.run_with}"
            )
        )

        inputs = {
            k: self._resolve_template_with_step(v) for k, v in step.inputs.items()
        }

        secrets = {}
        if step.secrets == "inherit":
            secrets = self._ctx.secrets.copy()
        elif isinstance(step.secrets, dict):
            secrets = step.secrets

        try:
            output_path = str(self._context_provider.get_output_path().absolute())
            wf_base_dir = self._context_provider.workflow.defaults.workflows_base_dir
            if wf_base_dir:
                workflow_name = Path(wf_base_dir) / workflow_name
            task_id = self._manager.add(
                workflow_name=str(workflow_name),
                ctx=RunContext(
                    inputs=inputs,
                    envs={**self._ctx.envs, **step.env},
                    secrets=secrets,
                    output_path=output_path,
                ),
                is_reused=True,
            )
            await self._manager.wait(task_id)
            flow_data = self._manager.get_runner(task_id)
            flow_runner = flow_data.get("runner", None) if flow_data else None

            if not flow_runner:
                raise RuntimeError(
                    f"Sub-workflow runner not found for task ID: {task_id}"
                )
            result = flow_runner.get_result()
            status = result.get("status", RunnerStatus.IDLE)
            if status != RunnerStatus.COMPLETED:
                error_msg = result.get("error", "Unknown error")
                raise RuntimeError(
                    f"Sub-workflow '{workflow_name}' failed: {error_msg}"
                )
            return result.get("outputs", {})
        except Exception as e:
            logger.error(
                self._produce_log(
                    f"(step '{step_name}') -> failed to execute sub-workflow '{workflow_name}': {e}"
                )
            )
            raise

    def _execute_subprocess(
        self, args: list, executable: str, step: Step, env: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        """
        Execute a subprocess with proper error handling and output capturing.

        Args:
            args: The arguments to pass to subprocess.run
            executable: The executable to run
            step: The step being executed

        Returns:
            Dict containing stdout and stderr

        Raises:
            RuntimeError: If the command fails
        """
        outputs = {}
        stderr = ""
        stdout = ""

        args = shlex.join(args)
        try:
            env = {**os.environ, **env}
            if step and step.env:
                env.update(step.env)

            output = subprocess.run(
                args,
                executable=executable,
                cwd=self._resolve_working_dir(step),
                env=env,
                timeout=(step.timeout_minutes * 60 if step else 60 * 24),
                capture_output=True,
                shell=True,
            )
            try:
                stderr = output.stderr.decode("utf-8").strip()
                stdout = output.stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                stderr = base64.b64encode(output.stderr).decode("utf-8")
                stdout = base64.b64encode(output.stdout).decode("utf-8")
                outputs["binary_output"] = True

            if output.returncode != 0:
                stderr = stderr or f"Command failed with exit code {output.returncode}"
                raise RuntimeError(f"Command failed: {stderr}")

        except subprocess.TimeoutExpired:
            stderr = f"Command timed out after {step.timeout_minutes} minutes"
            raise RuntimeError(stderr)

        except Exception as e:
            if not stderr:
                stderr = str(e)
            raise RuntimeError(f"Command error: {stderr}")

        outputs.update(
            {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": output.returncode if "output" in locals() else None,
            }
        )
        return outputs

    async def _handle_command(self, step: Step):
        """
        Execute a shell command as defined in the step.

        Args:
            step: The step configuration

        Returns:
            Dict containing the command output
        """
        default_shell = "/bin/bash"
        shell = default_shell
        for s in [
            step.shell,
            self._job.defaults.run.shell,
            self._context_provider.workflow.defaults.run.shell,
        ]:
            if s and s != default_shell:
                shell = s
                break
        script = step.run.strip()

        try:
            script = self._resolve_template_with_step(script)
        except Exception as e:
            raise RuntimeError(f"Failed to resolve template in command: {e}")

        logger.debug(
            self._produce_log(
                f"(step '{step.name}') -> executing command with shell {shell}"
            )
        )

        args = [shell, "-c", script]
        return self._execute_subprocess(args, shell, step, self._job.env)

    async def _handle_script(self, step: Step):
        """
        Execute a Python script as defined in the step.

        This method supports inline scripts or script files. For large scripts,
        it writes to a temporary file instead of passing via command line.

        Args:
            step: The step configuration

        Returns:
            Dict containing the script execution output
        """
        script = step.script.strip()
        tmp_file = None
        run_in_file = False

        try:
            if re.match(r"\w+_.*\.py", script):
                script_path = Path(step.working_directory or ".") / script
                if not script_path.exists():
                    raise FileNotFoundError(f"Script file not found: {script_path}")
                script = script_path.read_text().strip()

            script = self._resolve_template_with_step(script)

            python_executable = sys.executable

            enc_script = base64.b64encode(compress(script.encode(), 9)).decode()

            if len(enc_script) > 10000:
                run_in_file = True
                tmp_file = tempfile.mktemp(suffix=".py", dir=tempfile.gettempdir())
                with open(tmp_file, "w") as f:
                    f.write(f"import base64,zlib\n")
                    f.write(
                        f"exec(zlib.decompress(base64.b64decode('{enc_script}')).decode('utf-8'))\n"
                    )
                args = [python_executable, tmp_file]
            else:
                args = [
                    python_executable,
                    "-Wignore",
                    "-c",
                    f"import base64,zlib;exec(zlib.decompress(base64.b64decode('{enc_script}')).decode('utf-8'))",
                ]

            logger.debug(
                self._produce_log(f"(step '{step.name}') -> executing Python script")
            )

            return self._execute_subprocess(
                args, python_executable, step, self._job.env
            )
        except Exception as e:
            raise RuntimeError(f"Script execution failed: {str(e)}")

        finally:
            if run_in_file and tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception as e:
                    logger.warning(
                        self._produce_log(
                            f"Failed to remove temporary script file: {e}"
                        )
                    )

    def _produce_log(self, message: Any) -> str:
        """
        Format a log message with job context information.

        Args:
            message: The message to format

        Returns:
            str: Formatted log message with job context
        """
        job_name = self._job.name
        job_id = self._job_id
        status = self._status.value.upper()

        message_str = str(message)

        if hasattr(self, "_context_provider"):
            return self._context_provider._produce_log(
                f"(job '{job_id}' - '{job_name}')[{status}] -> {message_str}"
            )

        return f"[Job '{job_id}' - '{job_name}'][{status}] -> {message_str}"

    def _resolve_working_dir(self, step: Step) -> Path:
        """
        Resolve the working directory for a step.

        Args:
            step: The step configuration

        Returns:
            Path: The resolved working directory
        """
        step_path = Path(step.working_directory)
        if step_path.is_absolute():
            return step_path
        job_path = Path(self._job.defaults.run.working_directory)
        if job_path.is_absolute():
            return job_path / step_path
        workflow_path = Path(
            self._context_provider.workflow.defaults.run.working_directory
        )
        return workflow_path / job_path / step_path

    def _resolve_template_with_step(self, value: Any) -> Any:
        vars = {
            "steps": self._registered_steps_outputs,
            "needs": {
                k: self._context_provider._output_jobs[k] for k in self._job.needs
            },
        }
        logger.debug(
            self._produce_log(f"Resolving template for step with vars: {vars}")
        )
        return self._context_provider.resolve_template(value, vars)

    @property
    def processed_steps(self) -> int:
        """
        Get the number of processed steps.

        Returns:
            int: The number of steps that have been processed
        """
        return self._processed_steps

    @property
    def total_steps(self) -> int:
        """
        Get the total number of steps in the job.

        Returns:
            int: The total number of steps
        """
        return len(self._job.steps) if self._job and hasattr(self._job, "steps") else 0
