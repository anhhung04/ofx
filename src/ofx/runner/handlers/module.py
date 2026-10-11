"""Module step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.context import context_copy
from ofx.runner.handlers.registry import registry
from ofx.runner.run_defaults import resolve_model_shell


@registry.register(RunType.MODULE)
def create_runner(step_runner):
    """Build a ModuleRunner for a ``module:`` step."""
    from ofx.modules import ModuleInvocation, ModuleRunner

    assert step_runner.model.module is not None, (
        "module cannot be None for MODULE run type"
    )
    invocation = ModuleInvocation(
        name=step_runner.model.module,
        # Module args come from the merged context inputs: StepRunner._pre_run
        # already resolved the step's `with:` (run_with) args via the template
        # resolver and merged them into ctx.inputs (update_inputs), so the
        # context inputs are the single source of truth for module arguments
        # (workflow-level inputs plus step-level `with:` overrides).
        args=dict(step_runner.ctx.inputs),
        timeout_minutes=step_runner.model.timeout,
        shell=resolve_model_shell(step_runner, step_runner.model),
        working_directory=step_runner._resolve_working_dir(),
        interactive=step_runner.model.interactive and step_runner.ctx.allow_interactive,
    )
    return ModuleRunner(
        invocation,
        context_copy(step_runner.ctx),
        parent=step_runner,
    )
