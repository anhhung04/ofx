"""
Programmatic API for running OFX workflows.
"""

import asyncio
import logging
import re
import signal
import tempfile
import threading
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from ofx.models.config import DurableRunConfig
from ofx.models.workflow import Workflow
from ofx.runner.context import RunContext, RunResult, context_with_env
from ofx.runner.executors.workflow import WorkflowExecutor
from ofx.runner.registry import RegistryFactory
from ofx.runner.services.checkpoint import list_checkpoints
from ofx.runner.workflow import WorkflowRunner
from ofx.settings import (
    SECRETS_DIR,
    TEMP_DIR,
    ensure_dir,
    get_workflow_search_dirs,
    settings,
)
from ofx.utils.file_cleanup import remove_empty_dirs
from ofx.utils.log import register_secrets, register_sensitive_env
from ofx.utils.secrets import load_secrets_by_keys
from ofx.utils.workflow_utils import find_workflow, workflow_dirs_with_path

logger = logging.getLogger(settings.app_branding)

_SECRETS_DOT_RE = re.compile(r"\bsecrets\.([a-zA-Z_][a-zA-Z0-9_]*)")
_SECRETS_BRACKET_RE = re.compile(r"""secrets\[['"]([a-zA-Z_][a-zA-Z0-9_]*)["']\]""")

async def _build_run_runner(
    workflow: str | Path,
    *,
    inputs: dict[str, Any] | None,
    secrets: dict[str, str] | None,
    env: dict[str, str] | None,
    output_path: str | Path | None,
    workflow_search_paths: list[str | Path] | None,
    durable_overrides: DurableRunConfig | None,
    vars: dict[str, Any] | None,
    event_sink_path: Path | None,
    registry_backend: Literal["memory", "file", "redis", "memcached", "etcd"],
    registry_config: dict[str, Any] | None,
) -> tuple[WorkflowRunner, Path]:
    search_paths = [Path(path) for path in workflow_search_paths or get_workflow_search_dirs()]
    try:
        resolved_workflow = find_workflow(str(workflow), tuple(search_paths))
    except RuntimeError as exc:
        raise FileNotFoundError(f"Workflow {workflow!r} not found in search paths") from exc

    if output_path:
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path(
            tempfile.mkdtemp(
                prefix=f"run_{datetime.now().strftime('%d-%m-%Y_%H%M%S')}_",
                dir=ensure_dir(TEMP_DIR),
            )
        )
    if durable_overrides is not None:
        resolved_workflow.defaults.durable = durable_overrides
    durable_config = resolved_workflow.defaults.durable
    if durable_config and durable_config.enabled and not durable_config.resume:
        running_checkpoints = [
            checkpoint
            for checkpoint in await list_checkpoints(output_dir, durable_config)
            if checkpoint.get("status") == "running"
        ]
        if running_checkpoints:
            raise RuntimeError(
                "Durable checkpoints indicate in-progress execution in the output directory. "
                "Abort to avoid inconsistent state. In-progress: "
                + ", ".join(
                    checkpoint.get("name") or checkpoint.get("checkpoint_id") or "unknown"
                    for checkpoint in running_checkpoints
                )
            )
    if secrets is not None:
        runner_secrets = secrets
    else:
        try:
            needed: set[str] = set()
            if resolved_workflow.call and resolved_workflow.call.secrets:
                needed.update(resolved_workflow.call.secrets.keys())

            pending: list[Any] = [
                *(job.model_dump(mode="python") for job in resolved_workflow.jobs.values()),
                resolved_workflow.env,
            ]
            while pending:
                current = pending.pop()
                if isinstance(current, str):
                    needed.update(_SECRETS_DOT_RE.findall(current))
                    needed.update(_SECRETS_BRACKET_RE.findall(current))
                    continue
                if isinstance(current, dict):
                    pending.extend(current.values())
                    continue
                if isinstance(current, (list, tuple)):
                    pending.extend(current)

            runner_secrets = (
                load_secrets_by_keys(needed, secrets_dir=ensure_dir(SECRETS_DIR))
                if needed
                else {}
            )
        except Exception as exc:
            logger.warning(
                "Failed to load secrets: %s (continuing without secrets)", exc
            )
            runner_secrets = {}

    if runner_secrets:
        register_secrets(runner_secrets)
    if resolved_workflow.env:
        register_sensitive_env(resolved_workflow.env)
    ctx = RunContext(
        inputs=inputs or {},
        output_path=output_dir,
        secrets=runner_secrets,
        workflow_dirs=workflow_dirs_with_path(
            search_paths,
            resolved_workflow.workflow_path.parent,
        ),
        durable=durable_config,
        vars=vars or {},
        event_sink_path=event_sink_path,
    )
    if env:
        ctx = context_with_env(ctx, env)
    return (
        WorkflowRunner(
            resolved_workflow,
            ctx=ctx,
            registry=RegistryFactory.create(
                registry_backend,
                **(registry_config or {}),
            ),
            executor=WorkflowExecutor(),
        ),
        output_dir,
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
    event_sink_path: Path | None = None,
    registry_backend: Literal["memory", "file", "redis", "memcached", "etcd"] = "memory",
    registry_config: dict[str, Any] | None = None,
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
        event_sink_path: Optional path to write structured lifecycle events
            as newline-delimited JSON.
        registry_backend: Registry backend name to use for runner state.
        registry_config: Explicit backend configuration passed to the registry
            factory.

    Returns:
        RunResult object containing the execution status and outputs.

    Raises:
        FileNotFoundError: If the workflow file cannot be found.
        ValueError: If inputs break validation.
    """
    runner, output_dir = await _build_run_runner(
        workflow,
        inputs=inputs,
        secrets=secrets,
        env=env,
        output_path=output_path,
        workflow_search_paths=workflow_search_paths,
        durable_overrides=durable_overrides,
        vars=vars,
        event_sink_path=event_sink_path,
        registry_backend=registry_backend,
        registry_config=registry_config,
    )
    if quiet:
        runner.log_level = logging.ERROR

    loop = None
    registered_signals: list[int] = []
    if threading.current_thread() is threading.main_thread():
        loop = asyncio.get_running_loop()
        runner_task = asyncio.current_task()
        shutting_down = False

        def handle_shutdown(sig_num: int) -> None:
            nonlocal shutting_down
            sig_name = signal.Signals(sig_num).name
            if shutting_down:
                logger.warning("Received %s again — forcing exit", sig_name)
                raise SystemExit(128 + sig_num)
            shutting_down = True
            logger.warning(
                "Received %s — initiating graceful shutdown...", sig_name
            )
            if runner_task and not runner_task.done():
                runner_task.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError, OSError):
                loop.add_signal_handler(sig, handle_shutdown, sig)
                registered_signals.append(sig)
    try:
        return await runner.run()
    except asyncio.CancelledError:
        logger.warning("Workflow execution cancelled — collecting partial results")
        return await runner.get_result()
    finally:
        if loop is not None:
            for sig in registered_signals:
                with suppress(NotImplementedError, OSError):
                    loop.remove_signal_handler(sig)
        try:
            from ofx.runner.channels import close_channel_store

            close_channel_store()
        except Exception as e:
            logger.debug("Failed to close channel store: %s", e)

        for path in (output_dir, TEMP_DIR):
            remove_empty_dirs(path)
