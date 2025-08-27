import sys
import base64
import subprocess
import tempfile
import shlex
import logging

from zlib import compress
from pathlib import Path
from enum import Enum
from typing import Any

from ofx.models.step import Step
from ofx.runner.base import BaseRunner, RunContext, RunnerStatus
from ofx.settings import settings, BASE_DIR

logger = logging.getLogger(settings.app_branding)

DEFAULT_SHELL = "/bin/bash"


class RunType(Enum):
    SCRIPT = "script"
    COMMAND = "command"
    WORKFLOW = "workflow"


class CommandRunner(BaseRunner):
    def __init__(
        self,
        cmd: str,
        ctx: RunContext,
        shell: str | None = None,
        working_dir: Path | None = None,
        timeout_minutes: int = 1440,
        parent: BaseRunner | None = None,
    ):
        super().__init__("command", ctx, parent)
        self._cmd = cmd
        self._shell = shell
        self._cwd = working_dir or Path.cwd()
        self._timeout_minutes = timeout_minutes

    async def _do_run(self):
        stderr = ""
        stdout = ""
        if not Path(self._shell).exists():
            raise RuntimeError(f"Shell not found: {self._shell}")
        args = [self._shell, "-c", self._cmd]
        try:
            output = subprocess.run(
                args,
                cwd=self._cwd,
                env=self.ctx_vars.envs,
                timeout=self._timeout_minutes * 60,
                capture_output=True,
            )
            try:
                stderr = output.stderr.decode("utf-8").strip()
                stdout = output.stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                stderr = base64.b64encode(output.stderr).decode("utf-8")
                stdout = base64.b64encode(output.stdout).decode("utf-8")
                self._result.outputs["binary_output"] = True

            if output.returncode != 0:
                stderr = stderr or f"Command failed with exit code {output.returncode}"
                raise RuntimeError(f"Command failed: {stderr}")

        except subprocess.TimeoutExpired:
            stderr = f"Command timed out after {self._timeout_minutes} minutes"
            raise RuntimeError(stderr)

        except Exception as e:
            if not stderr:
                stderr = str(e)
            raise RuntimeError(f"Command error: {stderr}")
        self._result.outputs.update(
            {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": output.returncode if "output" in locals() else None,
            }
        )

    async def _pre_run(self):
        self._shell = self._resolve_shell()

    async def _post_run(self):
        if self.status != RunnerStatus.COMPLETED or self._error:
            logger.error(self._produce_log(f"Command failed: {self._error}"))
        logger.debug(
            self._produce_log(
                f"cmd result: \n---\n{self.get_result()}\n---\n with context: \n---\n{self.ctx_vars}\n---"
            )
        )

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        if self.parent:
            return self.parent._produce_log(
                f"(command)[{self.status.value.upper()}] -> {msg}"
            )
        return f"(command)[{self.status.value.upper()}] -> {msg}"

    def _resolve_shell(self) -> str:
        if self._shell:
            return self._shell
        if self.parent and self.parent.parent:
            parent_shell = getattr(self.parent.parent.model.defaults.run, "shell", None)
            if parent_shell:
                return parent_shell
            else:
                if hasattr(self.parent.parent.parent, "model"):
                    grandparent_shell = getattr(
                        self.parent.parent.parent.model.defaults.run, "shell", None
                    )
                    if grandparent_shell:
                        return grandparent_shell
        return DEFAULT_SHELL


class ScriptRunner(CommandRunner):

    def __init__(
        self,
        script: str,
        ctx: RunContext,
        shell: str | None = None,
        working_dir: Path | None = None,
        timeout_minutes: int = 1440,
        parent: BaseRunner | None = None,
    ):
        self._tmp_file = None
        self._run_in_file = False
        enc_script = base64.b64encode(compress(script.encode(), 9)).decode()
        python_executable = sys.executable or "python3"
        if len(enc_script) > 2000:
            self._run_in_file = True
            self._tmp_file = tempfile.mktemp(suffix=".py")
            with open(self._tmp_file, "w") as f:
                f.write(f"import base64,zlib\n")
                f.write(
                    f"exec(zlib.decompress(base64.b64decode('{enc_script}')).decode('utf-8'))\n"
                )
            args = [python_executable, self._tmp_file]
        else:
            args = [
                python_executable,
                "-Wignore",
                "-c",
                f"import base64,zlib;exec(zlib.decompress(base64.b64decode('{enc_script}')).decode('utf-8'))",
            ]
        super().__init__(
            cmd=shlex.join(args),
            shell=shell,
            working_dir=working_dir,
            timeout_minutes=timeout_minutes,
            parent=parent,
            ctx=ctx,
        )

    async def _post_run(self):
        if self._run_in_file and self._tmp_file and Path(self._tmp_file).exists():
            Path(self._tmp_file).unlink()
        if self.status != RunnerStatus.COMPLETED or self._error:
            logger.error(self._produce_log(f"Script failed: {self._error}"))


class StepRunner(BaseRunner):
    def __init__(
        self, step: Step, context: RunContext, parent: BaseRunner | None = None
    ):
        super().__init__(step, context, parent)
        self._model = step

    async def _pre_run(self):
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
        if self.model.log_stdout:
            stdout = self._result.outputs.get("stdout", "")
            if isinstance(stdout, str) and len(stdout) > 2000:
                stdout = stdout[:2000] + "\n...[truncated]"
            logger.info(self._produce_log(f"stdout:\n{stdout}\n"))
        logger.debug(self._produce_log(f"result: {self._result}"))

    async def _do_run(self):
        if self._run_type is RunType.WORKFLOW:
            from ofx.runner.workflow import WorkflowRunner

            runner = WorkflowRunner(
                WorkflowRunner.find_flow(self._model.uses),
                RunContext(
                    inputs=self._resolve_template(self._model.run_with),
                    envs=self.ctx_vars.envs,
                    output_path=self.parent.parent.ctx_vars.output_path,
                    secrets=(
                        self.ctx_vars.secrets
                        if self.model.secrets == "inherit"
                        else self._resolve_template(self.model.secrets)
                    ),
                ),
                parent=self,
            )
        elif self._run_type is RunType.SCRIPT:
            runner = ScriptRunner(
                self.model.script,
                self.ctx_vars.model_copy(),
                shell=self.model.shell,
                working_dir=self._resolve_working_dir(),
                parent=self,
                timeout_minutes=self.model.timeout,
            )
        elif self._run_type is RunType.COMMAND:
            runner = CommandRunner(
                self.model.run,
                self.ctx_vars.model_copy(),
                shell=self.model.shell,
                working_dir=self._resolve_working_dir(),
                parent=self,
                timeout_minutes=self.model.timeout,
            )
        res = await runner.run()
        self._status = res.status
        self._error = res.error
        for k, v in res.model_dump().items():
            setattr(self._result, k, v)
        logger.debug(self._produce_log(f"result: {self.get_result()}"))

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        msg = f"(step '{self._model.name}')[{self.status.value.upper()}] -> {msg}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _parse_run_type(self) -> RunType:
        """
        Determine the run type of a step based on its configuration.

        Args:
            step: The step to analyze

        Returns:
            RunType: The determined run type (SCRIPT, COMMAND, or WORKFLOW)

        Raises:
            ValueError: If the step doesn't define a valid run type
        """
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
        """
        Resolve the working directory for a step.

        Args:
            step: The step configuration

        Returns:
            Path: The resolved working directory
        """
        step = self._model
        step_path = Path(step.working_directory)
        if step_path.is_absolute():
            return step_path
        job_path = Path(self.parent.model.defaults.run.working_directory)
        if job_path.is_absolute():
            return job_path / step_path
        workflow_path = Path(self.parent.parent.model.defaults.run.working_directory)
        return workflow_path / job_path / step_path

    @property
    def model(self) -> Step:
        return self._model
