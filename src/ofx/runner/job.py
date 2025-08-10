import os
import uuid
import subprocess
import base64
import re
import sys
import tempfile
import logging
from ofx.runner.base import BaseRunner, RunnerStatus
from ofx.models.job import Job
from ofx.models.step import Step

from enum import Enum
from pathlib import Path
from zlib import compress

logger = logging.getLogger("ofx")


class RunType(Enum):
    SCRIPT = "script"
    COMMAND = "command"
    WORKFLOW = "workflow"


class JobRunner(BaseRunner):
    def __init__(self, job: Job):
        super().__init__(job.name)
        self._job = job
        self._id = str(uuid.uuid4())
        self._success = False

    async def run(self):
        await self._pre_run()
        try:
            self._status = RunnerStatus.RUNNING
            async for step_output in self._process_steps():
                yield step_output
            self._success = True
            self._status = RunnerStatus.COMPLETED
        except Exception as e:
            logger.error(f"Job '{self._job.name}' failed: {e}")
            self._success = False
            self._status = RunnerStatus.FAILED
        yield True

    async def _pre_run(self):
        if self._job.needs:
            if not all(
                self._context_provider.get_job_status(job_id) == RunnerStatus.COMPLETED
                for job_id in self._job.needs
            ):
                raise RuntimeError(
                    f"Job '{self._job.name}' cannot run because dependencies are not met: {self._job.needs}"
                )

    def attach_context_provider(self, context_provider):
        """
        Attach a context provider (like WorkflowRunner) that can resolve templates
        and provide secrets. This breaks the circular dependency.
        """
        self._context_provider = context_provider

    async def _process_steps(self):
        for step_id, step in enumerate(self._job.steps, start=1):
            run_type = self._parse_run_type(step)
            handler = self.__getattribute__(f"_handle_{run_type.value}")
            output = {}
            try:
                if not step.working_directory:
                    step.working_directory = os.getcwd()
                output = await handler(step)
                if isinstance(output, dict) and "stdout" in output:
                    logger.info(
                        f"Step '{step.name}' of job '{self._job.name}' produced outputs:\n{output['stdout']}"
                    )
                self._success = True
            except Exception as e:
                logger.error(
                    f"Error in step '{step.name}' of job '{self._job.name}': {e}"
                )
                self._success = False
            finally:
                yield {
                    "step": step.name,
                    "id": step_id,
                    "outputs": output,
                    "status": (
                        RunnerStatus.COMPLETED if self._success else RunnerStatus.FAILED
                    ),
                    "run_type": run_type,
                }

    def _parse_run_type(self, step: Step) -> RunType:
        if step.script:
            return RunType.SCRIPT
        elif step.run:
            return RunType.COMMAND
        elif step.uses:
            return RunType.WORKFLOW
        else:
            raise ValueError(f"Step '{step.name}' does not define a valid run type.")

    async def _handle_workflow(self, step: Step):
        logger.debug("subworkflow input: %s", step.run_with)
        # Use context provider instead of direct reference to workflow runner
        inputs = {
            k: self._context_provider.resolve_template(v) if isinstance(v, str) else v
            for k, v in step.run_with.items()
        }
        if step.secrets == "inherit":
            step.secrets = self._context_provider.get_default_secrets()
        task_id = self._manager.add(
            workflow_name=step.uses,
            inputs=inputs,
            is_reused=True,
            output=self._context_provider.get_output_path(),
            secrets={
                **step.secrets,
            },
        )
        await self._manager.wait(task_id)
        self._result = self._manager.get_runner(task_id)["task"].result
        return self._manager.get_runner(task_id)["runner"].get_result()

    async def _handle_command(self, step: Step):
        shell = step.shell or "/bin/bash"
        script = step.run.strip()
        script = self._context_provider.resolve_template(script)
        args = [shell, "-c", script]
        outputs = {}
        try:
            output = subprocess.run(
                args,
                executable=shell,
                cwd=step.working_directory,
                env={
                    **os.environ,
                    **self._job.env,
                    **step.env,
                },
                timeout=step.timeout_minutes * 60,
                capture_output=True,
            )
            stderr = output.stderr.decode("utf-8").strip()
            stdout = output.stdout.decode("utf-8").strip()
        except UnicodeDecodeError:
            stdout = base64.b64encode(output.stdout).decode("utf-8")
        except Exception as e:
            logger.debug(f"Error running command [{step.name}]({self._job.name}): {e}")
        finally:
            if stderr:
                raise RuntimeError(f"Command failed with error: {stderr}")
        outputs.update({"stdout": stdout, "stderr": stderr})
        return outputs

    async def _handle_script(self, step: Step):
        script = step.script.strip()
        outputs = {}
        if re.match(r"\w+_.*\.py", script):
            script = open(Path(step.working_directory) / script).read().strip()
        script = self._context_provider.resolve_template(script)
        python_executable = sys.executable
        enc_script = base64.b64encode(compress(script.encode(), 9)).decode()
        args = [
            python_executable,
            "-Wignore",
            "-c",
            f"import base64,zlib;exec(zlib.decompress(base64.b64decode('{enc_script}')))",
        ]
        run_in_file = False
        if len(enc_script) > 10000:
            tmp_file = tempfile.mktemp(suffix=".py", dir=tempfile.gettempdir())
            with open(tmp_file, "w") as f:
                f.write(f"import base64\n")
                f.write(f"exec(base64.b64decode('{enc_script}').decode('utf-8'))\n")
            args = [tmp_file]
            run_in_file = True

        try:
            output = subprocess.run(
                args,
                executable=python_executable,
                cwd=step.working_directory,
                env={
                    **os.environ,
                    **self._job.env,
                    **step.env,
                },
                timeout=step.timeout_minutes * 60,
                capture_output=True,
            )
            stderr = output.stderr.decode("utf-8").strip()
            stdout = output.stdout.decode("utf-8").strip()
        except UnicodeDecodeError:
            stdout = base64.b64encode(output.stdout).decode("utf-8")
        finally:
            if run_in_file:
                os.removedirs(tmp_file)
            if stderr:
                raise RuntimeError(f"Script execution failed with error: {stderr}")
        outputs.update({"stdout": stdout, "stderr": stderr})
        return outputs
