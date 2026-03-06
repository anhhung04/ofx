"""Custom exceptions for OFX framework.

Provides specific exception types for better error handling and debugging.
"""

from typing import Any


class OFXError(Exception):
    """Base exception for all OFX errors."""

    pass


class WorkflowError(OFXError):
    """Raised when workflow execution fails."""

    def __init__(
        self, message: str, workflow_name: str | None = None, job_id: str | None = None
    ):
        self.workflow_name = workflow_name
        self.job_id = job_id
        super().__init__(message)


class JobError(OFXError):
    """Raised when job execution fails."""

    def __init__(
        self, message: str, job_id: str | None = None, step_id: str | None = None
    ):
        self.job_id = job_id
        self.step_id = step_id
        super().__init__(message)


class StepError(OFXError):
    """Raised when step execution fails."""

    def __init__(
        self, message: str, step_id: str | None = None, exit_code: int | None = None
    ):
        self.step_id = step_id
        self.exit_code = exit_code
        super().__init__(message)


class TemplateError(OFXError):
    """Raised when template resolution fails."""

    pass


class ConfigurationError(OFXError):
    """Raised when configuration is invalid."""

    pass


class DependencyError(OFXError):
    """Raised when workflow dependencies cannot be resolved."""

    def __init__(self, message: str, missing_deps: list[Any] | None = None):
        self.missing_deps = missing_deps or []
        super().__init__(message)


class TimeoutError(OFXError):
    """Raised when operation times out."""

    def __init__(self, message: str, timeout_seconds: int | None = None):
        self.timeout_seconds = timeout_seconds
        super().__init__(message)


class APIError(OFXError):
    """Raised when API operations fail."""

    def __init__(
        self, message: str, status_code: int | None = None, response: str | None = None
    ):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class SecretError(OFXError):
    """Raised when secret operations fail."""

    pass


class ToolError(OFXError):
    """Raised when tool installation or execution fails."""

    def __init__(self, message: str, tool_name: str | None = None):
        self.tool_name = tool_name
        super().__init__(message)
