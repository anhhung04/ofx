"""
Programmatic API for running OFX workflows.
"""

import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ofx.models.config import DurableRunConfig
from ofx.models.workflow import Workflow
from ofx.runner.context import RunContext
from ofx.runner.core import RunResult
from ofx.runner.core.durable import find_running_checkpoints
from ofx.runner.execution.workflow import WorkflowRunner
from ofx.settings import (
    SECRETS_DIR,
    TEMP_DIR,
    ensure_dir,
    get_workflow_search_dirs,
    settings,
)
from ofx.utils.log import register_secrets, register_sensitive_env
from ofx.utils.secrets import load_secrets_by_keys
from ofx.utils.workflow_utils import add_workflow_dir, find_workflow

logger = logging.getLogger(settings.app_branding)

# Matches secrets.KEY_NAME in Jinja2 template expressions.
# Handles both dot access (secrets.MY_KEY) and bracket access (secrets["MY_KEY"]).
_SECRETS_DOT_RE = re.compile(r"\bsecrets\.([a-zA-Z_][a-zA-Z0-9_]*)")
_SECRETS_BRACKET_RE = re.compile(r"""secrets\[['"]([a-zA-Z_][a-zA-Z0-9_]*)["']\]""")


def _extract_secret_refs(workflow: Workflow) -> set[str]:
    """Scan a workflow model for secret name references in template strings.

    Walks all string values in the workflow dump looking for patterns like
    ``secrets.MY_KEY`` or ``secrets["MY_KEY"]``.  Also includes keys
    declared in ``call.secrets`` for reusable workflows.
    """
    refs: set[str] = set()

    # Declared secrets in call config (reusable workflows)
    if workflow.call and workflow.call.secrets:
        refs.update(workflow.call.secrets.keys())

    # Walk the model dump looking for template references
    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            refs.update(_SECRETS_DOT_RE.findall(obj))
            refs.update(_SECRETS_BRACKET_RE.findall(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                _walk(v)

    # Dump jobs (where templates live) — exclude heavy non-template fields
    for job in workflow.jobs.values():
        _walk(job.model_dump(mode="python"))

    # Also scan workflow-level env (may reference secrets)
    _walk(workflow.env)

    return refs


def _cleanup_run(output_dir: Path) -> None:
    """Clean up temp artifacts after a workflow run."""
    # 1. Close channel store (removes channel files + dir)
    try:
        from ofx.runner.channels import close_channel_store

        close_channel_store()
    except Exception:
        pass

    # 2. Remove empty output subdirectories (bottom-up)
    if output_dir and output_dir.exists():
        _remove_empty_dirs(output_dir)

    # 3. Clean up TEMP_DIR if empty
    try:
        if TEMP_DIR.exists():
            _remove_empty_dirs(TEMP_DIR)
    except Exception:
        pass


def _remove_empty_dirs(root: Path) -> None:
    """Remove empty directories bottom-up under *root*, including *root* itself."""
    if not root.is_dir():
        return
    for child in sorted(root.rglob("*"), reverse=True):
        if child.is_dir():
            try:
                child.rmdir()  # only succeeds if empty
            except OSError:
                pass
    try:
        root.rmdir()
    except OSError:
        pass


def _get_tmp_dir(output: str | Path | None = None) -> Path:
    """Get the temporary directory for workflow runs"""
    if output and Path(output).is_dir():
        return Path(output)
    if output:
        # If output path is provided but doesn't exist, create it
        p = Path(output)
        p.mkdir(parents=True, exist_ok=True)
        return p

    return Path(
        tempfile.mkdtemp(
            prefix=f"run_{datetime.now().strftime('%d-%m-%Y_%H%M%S')}_",
            dir=ensure_dir(TEMP_DIR),
        )
    )


async def run_workflow(
    workflow: str | Path,
    inputs: dict[str, Any] | None = None,
    secrets: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    output_path: str | Path | None = None,
    workflow_search_paths: list[str | Path] | None = None,
    quiet: bool = False,
    durable_overrides: DurableRunConfig | None = None,
    vars: dict[str, Any] | None = None,
) -> RunResult:
    """
    Run an OFX workflow programmatically.

    Args:
        workflow: Name of the workflow (to be searched) or path to the workflow file.
        inputs: Dictionary of input values.
        secrets: Dictionary of secrets (overrides default secrets loading).
        env: Dictionary of extra environment variables to inject into the run context.
            These are merged on top of the inherited os.environ.
        output_path: Directory for outputs. Defaults to a unique temp dir.
        workflow_search_paths: List of directories to search for workflows.
            Defaults to standard OFX workflow directories if not provided.
        quiet: If True, suppresses console output (sets log level to ERROR).
        durable_overrides: Override durable execution configuration.
        vars: Dictionary of additional variables to inject into the run context
            (e.g. project metadata).

    Returns:
        RunResult object containing the execution status and outputs.

    Raises:
        FileNotFoundError: If the workflow file cannot be found.
        ValueError: If inputs break validation.
    """
    search_paths = workflow_search_paths or get_workflow_search_dirs()
    search_paths = [Path(p) for p in search_paths]

    try:
        resolved_workflow: Workflow = find_workflow(str(workflow), tuple(search_paths))
    except RuntimeError as exc:
        raise FileNotFoundError(
            f"Workflow {workflow!r} not found in search paths"
        ) from exc

    output_dir = _get_tmp_dir(output_path)
    if durable_overrides is not None:
        resolved_workflow.defaults.durable = durable_overrides
    durable_config = resolved_workflow.defaults.durable
    if durable_config and durable_config.enabled:
        running_checkpoints = await find_running_checkpoints(output_dir, durable_config)
        if running_checkpoints and not durable_config.resume:
            names = [
                (checkpoint.get("name") or checkpoint.get("checkpoint_id") or "unknown")
                for checkpoint in running_checkpoints
            ]
            raise RuntimeError(
                "Durable checkpoints indicate in-progress execution in the output directory. "
                f"Abort to avoid inconsistent state. In-progress: {', '.join(names)}"
            )

    runner_secrets = secrets
    if runner_secrets is None:
        try:
            needed = _extract_secret_refs(resolved_workflow)
            if needed:
                runner_secrets = load_secrets_by_keys(
                    needed, secrets_dir=ensure_dir(SECRETS_DIR)
                )
            else:
                runner_secrets = {}
        except Exception:
            runner_secrets = {}

    # Register secret values for log redaction *before* any runner logs.
    if runner_secrets:
        register_secrets(runner_secrets)
    # Redact sensitive-looking env vars (passwords, tokens, keys) from logs.
    if resolved_workflow.env:
        register_sensitive_env(resolved_workflow.env)

    ctx = RunContext(
        inputs=inputs or {},
        output_path=output_dir,
        secrets=runner_secrets,
        workflow_dirs=add_workflow_dir(
            search_paths, resolved_workflow.workflow_path.parent
        ),
        durable=durable_config,
        vars=vars or {},
    )

    # Merge explicit env vars on top of inherited os.environ
    if env:
        ctx.envs.update(env)

    runner = WorkflowRunner(resolved_workflow, ctx=ctx)

    if quiet:
        runner.log_level = logging.ERROR

    try:
        result = await runner.run()
        return result
    finally:
        _cleanup_run(output_dir)
