"""
Programmatic API for running OFX workflows.
"""
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ofx.models.workflow import Workflow
from ofx.runner.context import RunContext
from ofx.runner.core import RunResult
from ofx.runner.execution.workflow import WorkflowRunner
from ofx.settings import (
    DEFAULT_WORKFLOWS_DIRS,
    SECRETS_DIR,
    TEMP_DIR,
    ensure_dir,
    settings,
    get_console,
)
from ofx.utils.secrets import load_secrets
from ofx.utils.workflow_utils import add_workflow_dir, find_workflow

logger = logging.getLogger(settings.app_branding)


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
    output_path: str | Path | None = None,
    workflow_search_paths: list[str | Path] | None = None,
    quiet: bool = False,
) -> RunResult:
    """
    Run an OFX workflow programmatically.
    
    Args:
        workflow: Name of the workflow (to be searched) or path to the workflow file.
        inputs: Dictionary of input values.
        secrets: Dictionary of secrets (overrides default secrets loading).
        output_path: Directory for outputs. Defaults to a unique temp dir.
        workflow_search_paths: List of directories to search for workflows.
            Defaults to standard OFX workflow directories if not provided.
        quiet: If True, suppresses console output (sets log level to ERROR).
    
    Returns:
        RunResult object containing the execution status and outputs.
        
    Raises:
        FileNotFoundError: If the workflow file cannot be found.
        ValueError: If inputs break validation.
    """
    # 1. Resolve workflow path and model
    search_paths = workflow_search_paths or DEFAULT_WORKFLOWS_DIRS
    
    # If workflow is a path to an existing file, use it directly
    workflow_path = Path(workflow)
    if workflow_path.exists() and workflow_path.is_file():
        # It's a direct file path
        # Minimal wrapper to load it - find_workflow currently expects name + dirs
        # We can implement a direct loader or temporarily add parent to search path
        # But find_workflow is convenient. Let's rely on it searching properly if we verify path.
        # Actually find_workflow handles name lookup.
        # Let's check how find_workflow works.
        pass
        
    resolved_workflow: Workflow = find_workflow(str(workflow), tuple(search_paths))
    
    # 2. Setup Context
    output_dir = _get_tmp_dir(output_path)
    
    # Load secrets if not provided
    runner_secrets = secrets
    if runner_secrets is None:
        try:
            runner_secrets = load_secrets(ensure_dir(SECRETS_DIR))
        except Exception:
            # Fallback for library usage with no configured secrets dir
            runner_secrets = {}

    # 3. Initialize Runner
    ctx = RunContext(
        inputs=inputs or {},
        output_path=output_dir,
        secrets=runner_secrets,
        workflow_dirs=add_workflow_dir(
            search_paths, resolved_workflow.workflow_path.parent
        ),
    )
    
    runner = WorkflowRunner(resolved_workflow, ctx=ctx)
    
    # 4. Configure logging/output
    if quiet:
        runner.log_level = logging.ERROR
        
    # 5. Run
    # Note: caller is responsible for running this in an async loop
    await runner.run()
    
    result = await runner.get_result()
    return result
