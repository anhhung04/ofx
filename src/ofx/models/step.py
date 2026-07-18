"""Step model for workflow execution."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from ofx.models.base import OFXBaseModel
from ofx.settings import DEFAULT_SHELL

class RunType(Enum):
    """Type of step execution."""

    SCRIPT = "script"
    COMMAND = "command"
    WORKFLOW = "workflow"
    SCRIPT_FILE = "script_file"
    TASK = "task"
    PIPE = "pipe"

class Step(OFXBaseModel):
    """Step definition within a job."""

    name: str = Field(default="<should_be_replaced>", description="Name of the step")
    run_if: str | bool = Field(
        default=True,
        description="Condition to run the step (e.g., 'success()', 'failure()')",
        alias="if",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for the step",
    )
    continue_on_error: bool = Field(
        default=False,
        description="Continue execution even if the step fails",
        alias="continue-on-error",
    )
    timeout: int | str = Field(
        default=60 * 24,
        description="Timeout in minutes for the step execution. Supports Jinja2 templates for dynamic values.",
    )
    retry: int = Field(
        default=0,
        description="Number of retry attempts on failure (default: 0, no retries)",
    )
    retry_delay: int = Field(
        default=5,
        description="Delay in seconds between retry attempts (default: 5)",
        alias="retry-delay",
    )
    shell: str = Field(
        default=DEFAULT_SHELL,
        description="Shell to use for running commands in the step",
    )
    working_directory: Path = Field(
        default_factory=Path.cwd,
        description="Working directory for the step execution",
        alias="working-directory",
    )
    log_stdout: bool | str = Field(
        default=False,
        description="Whether to capture standard output of the step",
        alias="log-stdout",
    )
    log_command: bool | str = Field(
        default=False,
        description="Whether to log the executed command to the command log (defaults to <project_path>/logs/command_log.ndjson)",
        alias="log-command",
    )
    uses: str | None = Field(
        default=None,
        description="Select a workflow to run as part of a step in the job",
    )
    run: str | None = Field(default=None, description="Command(s) to run in the step")
    script: str | None = Field(
        default=None, description="Script to run in the step (if applicable)"
    )
    script_file: str | None = Field(
        default=None, description="Path to a Python script file to execute"
    )
    task: str | None = Field(
        default=None,
        description="Name of a registered task (pre-built tool wrapper) to execute",
    )
    run_with: dict[str, Any] = Field(
        default_factory=dict,
        description="Define inputs for the step if it uses a reusable workflow",
        alias="with",
    )
    secrets: dict[str, str] | Literal["inherit"] = Field(
        default_factory=dict,
        description="Secrets to pass to the step (key-value pairs) if it uses a reusable workflow",
    )
    interactive: bool = Field(
        default=False,
        description="Enable interactive mode (stdin/stdout passthrough). Only works in single-job stages.",
    )
    pipe: Any = Field(
        default=None,
        description=(
            "Declarative ETL pipeline. Accepts a PipeConfig dict with "
            "input, filter, map, sort, unique, format, etc."
        ),
    )
    store_creds: bool | None = Field(
        default=None,
        description=(
            "Store discovered UserAccount credentials from task outputs "
            "into the credential store. Overrides the global auto_store_creds setting. "
            "Only applies to task steps."
        ),
        alias="store-creds",
    )
    step_index: int = Field(
        default=-1, description="Index of the step in the job (set during execution)"
    )

    @model_validator(mode="after")
    def check_run_type(self):
        """Validate step configuration.

        - Exactly one of 'run', 'script', 'uses', 'script_file', 'task', or 'pipe'.
        - timeout must be positive (when numeric).
        - retry/retry_delay must be non-negative.
        """
        defined_fields = sum(
            1
            for field in ["run", "script", "uses", "script_file", "task", "pipe"]
            if getattr(self, field) is not None
        )
        if defined_fields != 1:
            raise ValueError(
                f"Step '{self.name}' must have exactly one of 'run', 'script', "
                f"'script_file', 'uses', 'task', or 'pipe' defined."
            )

        if isinstance(self.timeout, int) and self.timeout <= 0:
            raise ValueError(
                f"Step '{self.name}' timeout must be positive, got {self.timeout}"
            )
        if self.retry < 0:
            raise ValueError(
                f"Step '{self.name}' retry must be non-negative, got {self.retry}"
            )
        if self.retry_delay < 0:
            raise ValueError(
                f"Step '{self.name}' retry_delay must be non-negative, got {self.retry_delay}"
            )

        if self.pipe is not None:
            from ofx.models.pipe import PipeConfig

            if isinstance(self.pipe, dict):
                self.pipe = PipeConfig.model_validate(self.pipe)
            elif not isinstance(self.pipe, PipeConfig):
                raise ValueError(
                    f"Step '{self.name}' pipe must be a dict or PipeConfig, "
                    f"got {type(self.pipe).__name__}"
                )

        return self

    def get_run_type(self) -> RunType:
        if self.uses:
            return RunType.WORKFLOW
        elif self.script:
            return RunType.SCRIPT
        elif self.script_file:
            return RunType.SCRIPT_FILE
        elif self.task:
            return RunType.TASK
        elif self.pipe is not None:
            return RunType.PIPE
        elif self.run:
            return RunType.COMMAND
        raise ValueError(
            f"Step '{self.name}' must have one of 'run', 'script', 'script_file', "
            f"'uses', 'task', or 'pipe' defined."
        )
