"""Workflow validation utilities.

Validates workflow configuration before execution to catch errors early.
"""

from pathlib import Path
from typing import List, Set, Dict, Any
from collections import deque

from ofx.models.workflow import Workflow
from ofx.models.job import Job
from ofx.models.step import Step


class ValidationError:
    """Represents a validation error."""
    
    def __init__(self, severity: str, message: str, location: str = None):
        self.severity = severity  # 'error' or 'warning'
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
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
    
    def validate(self) -> tuple[List[ValidationError], List[ValidationError]]:
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
            self.errors.append(ValidationError(
                "error",
                "Workflow must have at least one job"
            ))
            return
        
        job_ids = set(self.workflow.jobs.keys())
        
        # Check for duplicate job IDs
        if len(job_ids) != len(self.workflow.jobs):
            self.errors.append(ValidationError(
                "error",
                "Duplicate job IDs found"
            ))
        
        # Check job names
        for job_id, job in self.workflow.jobs.items():
            if not job.name and not job_id:
                self.warnings.append(ValidationError(
                    "warning",
                    f"Job '{job_id}' has no name",
                    f"jobs.{job_id}"
                ))
            
            if not job.steps:
                self.errors.append(ValidationError(
                    "error",
                    f"Job '{job_id}' has no steps",
                    f"jobs.{job_id}"
                ))
    
    def _validate_dependencies(self):
        """Validate job dependencies and check for cycles."""
        jobs = self.workflow.jobs
        job_ids = set(jobs.keys())
        
        # Build dependency graph
        graph: Dict[str, List[str]] = {jid: [] for jid in job_ids}
        
        for job_id, job in jobs.items():
            if job.needs:
                needs = [job.needs] if isinstance(job.needs, str) else job.needs
                
                for dep in needs:
                    # Check if dependency exists
                    if dep not in job_ids:
                        self.errors.append(ValidationError(
                            "error",
                            f"Job '{job_id}' depends on '{dep}', which doesn't exist",
                            f"jobs.{job_id}.needs"
                        ))
                    else:
                        graph[dep].append(job_id)
        
        # Detect circular dependencies using DFS
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
                    self.errors.append(ValidationError(
                        "error",
                        "Circular dependency detected in job dependencies"
                    ))
                    break
    
    def _validate_steps(self):
        """Validate step configuration."""
        for job_id, job in self.workflow.jobs.items():
            for idx, step in enumerate(job.steps):
                step_loc = f"jobs.{job_id}.steps[{idx}]"
                
                # Check that step has at least one action
                has_action = any([step.run, step.script, step.uses])
                if not has_action:
                    self.errors.append(ValidationError(
                        "error",
                        f"Step '{step.name or idx}' must have 'run', 'script', or 'uses'",
                        step_loc
                    ))
                
                # Check for multiple actions
                action_count = sum([bool(step.run), bool(step.script), bool(step.uses)])
                if action_count > 1:
                    self.errors.append(ValidationError(
                        "error",
                        f"Step '{step.name or idx}' has multiple actions (run/script/uses)",
                        step_loc
                    ))
                
                # Validate 'uses' path
                if step.uses:
                    if not isinstance(step.uses, str):
                        self.errors.append(ValidationError(
                            "error",
                            f"Step '{step.name or idx}' 'uses' must be a string",
                            step_loc
                        ))
                
                # Check timeout
                if step.timeout and step.timeout <= 0:
                    self.warnings.append(ValidationError(
                        "warning",
                        f"Step '{step.name or idx}' has invalid timeout: {step.timeout}",
                        step_loc
                    ))
    
    def _validate_template_syntax(self):
        """Validate template syntax (basic check)."""
        # This is a simplified check - full validation would need Jinja2 parsing
        def check_templates(obj: Any, location: str = ""):
            if isinstance(obj, str):
                # Check for unclosed templates
                open_count = obj.count("${{")
                close_count = obj.count("}}")
                if open_count != close_count:
                    self.warnings.append(ValidationError(
                        "warning",
                        "Possibly unclosed template expression",
                        location
                    ))
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    check_templates(value, f"{location}.{key}" if location else key)
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    check_templates(item, f"{location}[{idx}]")
        
        check_templates(self.workflow.model_dump())
    
    def _validate_secrets(self):
        """Validate secret references."""
        # Check if secrets are referenced but not defined in workflow
        # This is a basic check - full validation would need runtime context
        
        for job_id, job in self.workflow.jobs.items():
            for idx, step in enumerate(job.steps):
                if step.secrets and step.secrets != "inherit":
                    if not isinstance(step.secrets, dict):
                        self.warnings.append(ValidationError(
                            "warning",
                            f"Step '{step.name or idx}' secrets should be a dict or 'inherit'",
                            f"jobs.{job_id}.steps[{idx}].secrets"
                        ))
    
    def _validate_inputs(self):
        """Validate workflow inputs."""
        if self.workflow.inputs:
            for input_name, input_spec in self.workflow.inputs.items():
                # Check required inputs have no default
                if input_spec.required and input_spec.default is not None:
                    self.warnings.append(ValidationError(
                        "warning",
                        f"Required input '{input_name}' has a default value",
                        f"inputs.{input_name}"
                    ))
    
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
    'ValidationError',
    'WorkflowValidator',
    'validate_workflow',
    'validate_workflow_file',
]
