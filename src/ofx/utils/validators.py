"""Workflow validation utilities.

Validates workflow configuration before execution to catch errors early.
"""

from pathlib import Path
from typing import Any

from ofx.models.workflow import Workflow


def validate_aliases(inputs):
    input_names = set(inputs.keys())
    aliases = set()
    for input_name, input_model in inputs.items():
        alias = input_model.alias
        if alias is not None:
            if alias == input_name:
                raise ValueError(
                    f"Input '{input_name}' has an alias identical to its name."
                )
            elif alias in input_names:
                raise ValueError(
                    f"Input '{input_name}' has an alias '{alias}' that conflicts with another input name."
                )
            elif alias in aliases:
                raise ValueError(
                    f"Alias '{alias}' is used by multiple inputs, causing a conflict."
                )
            aliases.add(alias)
    return True


class ValidationError:
    """Represents a validation error."""

    def __init__(self, severity: str, message: str, location: str = ""):
        self.severity = severity
        self.message = message
        self.location = location

    def __str__(self):
        prefix = "❌" if self.severity == "error" else "⚠️"
        location = f" [{self.location}]" if self.location else ""
        return f"{prefix} {self.message}{location}"


class WorkflowValidator:
    """Validates workflow configuration."""

    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        self.errors: list[ValidationError] = []
        self.warnings: list[ValidationError] = []

    def validate(self) -> tuple[list[ValidationError], list[ValidationError]]:
        """Run all validation checks."""
        self._validate_jobs()
        self._validate_dependencies()
        self._validate_steps()
        self._validate_template_syntax()
        self._validate_secrets()
        self._validate_inputs()

        return self.errors, self.warnings

    def _validate_jobs(self):
        """Validate job configuration."""
        if not self.workflow.jobs:
            self.errors.append(
                ValidationError("error", "Workflow must have at least one job")
            )
            return

        job_ids = set(self.workflow.jobs.keys())

        if len(job_ids) != len(self.workflow.jobs):
            self.errors.append(ValidationError("error", "Duplicate job IDs found"))

        for job_id, job in self.workflow.jobs.items():
            if not job.name and not job_id:
                self.warnings.append(
                    ValidationError(
                        "warning", f"Job '{job_id}' has no name", f"jobs.{job_id}"
                    )
                )

            if not job.steps:
                self.errors.append(
                    ValidationError(
                        "error", f"Job '{job_id}' has no steps", f"jobs.{job_id}"
                    )
                )

    def _validate_dependencies(self):
        """Validate job dependencies and check for cycles."""
        jobs = self.workflow.jobs
        job_ids = set(jobs.keys())

        graph: dict[str, list[str]] = {jid: [] for jid in job_ids}

        for job_id, job in jobs.items():
            if job.needs:
                needs = [job.needs] if isinstance(job.needs, str) else job.needs

                for dep in needs:
                    if dep not in job_ids:
                        self.errors.append(
                            ValidationError(
                                "error",
                                f"Job '{job_id}' depends on '{dep}', which doesn't exist",
                                f"jobs.{job_id}.needs",
                            )
                        )
                    else:
                        graph[dep].append(job_id)

        visited = set()
        rec_stack = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for job_id in job_ids:
            if job_id not in visited:
                if has_cycle(job_id):
                    self.errors.append(
                        ValidationError(
                            "error", "Circular dependency detected in job dependencies"
                        )
                    )
                    break

    def _validate_steps(self):
        """Validate step configuration."""
        for job_id, job in self.workflow.jobs.items():
            for idx, step in enumerate(job.steps):
                step_loc = f"jobs.{job_id}.steps[{idx}]"

                has_action = any([step.run, step.script, step.uses])
                if not has_action:
                    self.errors.append(
                        ValidationError(
                            "error",
                            f"Step '{step.name or idx}' must have 'run', 'script', or 'uses'",
                            step_loc,
                        )
                    )

                action_count = sum([bool(step.run), bool(step.script), bool(step.uses)])
                if action_count > 1:
                    self.errors.append(
                        ValidationError(
                            "error",
                            f"Step '{step.name or idx}' has multiple actions (run/script/uses)",
                            step_loc,
                        )
                    )

                if step.uses:
                    if not isinstance(step.uses, str):
                        self.errors.append(
                            ValidationError(
                                "error",
                                f"Step '{step.name or idx}' 'uses' must be a string",
                                step_loc,
                            )
                        )

                if step.timeout and step.timeout <= 0:
                    self.warnings.append(
                        ValidationError(
                            "warning",
                            f"Step '{step.name or idx}' has invalid timeout: {step.timeout}",
                            step_loc,
                        )
                    )

    def _validate_template_syntax(self):
        """Validate template syntax (basic check)."""

        def check_templates(obj: Any, location: str = ""):
            if isinstance(obj, str):
                open_count = obj.count("{{")
                close_count = obj.count("}}")
                if open_count != close_count:
                    self.warnings.append(
                        ValidationError(
                            "warning", "Possibly unclosed template expression", location
                        )
                    )
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    check_templates(value, f"{location}.{key}" if location else key)
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    check_templates(item, f"{location}[{idx}]")

        check_templates(self.workflow.model_dump())

    def _validate_secrets(self):
        """Validate secret references."""
        for job_id, job in self.workflow.jobs.items():
            for idx, step in enumerate(job.steps):
                if step.secrets and step.secrets != "inherit":
                    if not isinstance(step.secrets, dict):
                        self.warnings.append(
                            ValidationError(
                                "warning",
                                f"Step '{step.name or idx}' secrets should be a dict or 'inherit'",
                                f"jobs.{job_id}.steps[{idx}].secrets",
                            )
                        )

    def _validate_inputs(self):
        """Validate workflow inputs."""
        inputs = (
            self.workflow.call.inputs
            if self.workflow.call
            else (self.workflow.dispatch.inputs if self.workflow.dispatch else {})
        )
        if not inputs:
            return
        for input_name, input_spec in inputs.items():
            if input_spec.required and input_spec.default is not None:
                self.warnings.append(
                    ValidationError(
                        "warning",
                        f"Required input '{input_name}' has a default value",
                        f"inputs.{input_name}",
                    )
                )
        try:
            validate_aliases(inputs)
        except Exception as e:
            self.errors.append(ValidationError("error", str(e), "inputs"))

    def is_valid(self) -> bool:
        """Check if workflow is valid (no errors)."""
        return len(self.errors) == 0

    def report(self) -> str:
        """Generate a validation report."""
        lines = []

        if not self.errors and not self.warnings:
            lines.append("✅ Workflow validation passed!")
            return "\n".join(lines)

        if self.errors:
            lines.append(f"❌ Found {len(self.errors)} error(s):")
            for error in self.errors:
                lines.append(f"   {error}")
            lines.append("")

        if self.warnings:
            lines.append(f"⚠️  Found {len(self.warnings)} warning(s):")
            for warning in self.warnings:
                lines.append(f"   {warning}")

        return "\n".join(lines)


def validate_workflow(workflow: Workflow) -> tuple[bool, str]:
    """Validate a workflow and return (is_valid, report).

    Args:
        workflow: The workflow to validate

    Returns:
        Tuple of (is_valid, report_string)

    Example:
        >>> is_valid, report = validate_workflow(workflow)
        >>> print(report)
        >>> if not is_valid:
        >>>     raise ValueError("Workflow validation failed")
    """
    validator = WorkflowValidator(workflow)
    validator.validate()
    return validator.is_valid(), validator.report()


def validate_workflow_file(workflow_path: Path) -> tuple[bool, str]:
    """Validate a workflow file.

    Args:
        workflow_path: Path to workflow YAML file

    Returns:
        Tuple of (is_valid, report_string)
    """
    import yaml

    with open(workflow_path) as f:
        workflow_dict = yaml.safe_load(f)

    workflow = Workflow(**workflow_dict)
    return validate_workflow(workflow)


__all__ = [
    "ValidationError",
    "WorkflowValidator",
    "validate_workflow",
    "validate_workflow_file",
]
