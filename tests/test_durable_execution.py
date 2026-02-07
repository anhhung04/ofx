from pathlib import Path

import pytest

from ofx.models.config import DurableRunConfig
from ofx.runner.api import run_workflow
from ofx.runner.core import RunnerStatus
from ofx.runner.core.durable import (
    get_checkpoint,
    list_checkpoints,
    write_checkpoint,
)


@pytest.mark.asyncio
async def test_durable_resume_skips_execution(tmp_path: Path) -> None:
    workflow_path = Path(__file__).parent / "flows" / "durable.yml"
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]

    result_first = await run_workflow(
        workflow=workflow_path,
        output_path=tmp_path,
        workflow_search_paths=workflow_dirs,
    )
    assert result_first.status == RunnerStatus.COMPLETED

    output_file = tmp_path / "durable.txt"
    assert output_file.exists()
    first_lines = output_file.read_text().splitlines()
    assert len(first_lines) == 1

    result_second = await run_workflow(
        workflow=workflow_path,
        output_path=tmp_path,
        workflow_search_paths=workflow_dirs,
    )
    assert result_second.status == RunnerStatus.COMPLETED

    second_lines = output_file.read_text().splitlines()
    assert len(second_lines) == 1


@pytest.mark.asyncio
async def test_durable_abort_on_running_checkpoint(tmp_path: Path) -> None:
    workflow_path = Path(__file__).parent / "flows" / "durable.yml"
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]

    durable_config = DurableRunConfig(enabled=True, resume=False, backend="file")
    await write_checkpoint(
        tmp_path,
        durable_config,
        "workflow/WorkflowRunner:Durable Test",
        {"status": "running"},
    )

    with pytest.raises(RuntimeError, match="in-progress execution"):
        await run_workflow(
            workflow=workflow_path,
            output_path=tmp_path,
            workflow_search_paths=workflow_dirs,
            durable_overrides=durable_config,
        )


@pytest.mark.asyncio
async def test_durable_list_and_get_checkpoints(tmp_path: Path) -> None:
    durable_config = DurableRunConfig(enabled=True, resume=True, backend="file")
    await write_checkpoint(
        tmp_path,
        durable_config,
        "workflow/WorkflowRunner:One",
        {"status": "completed", "checkpoint_id": "one"},
    )
    await write_checkpoint(
        tmp_path,
        durable_config,
        "workflow/WorkflowRunner:Two",
        {"status": "failed", "checkpoint_id": "two"},
    )

    checkpoints = await list_checkpoints(tmp_path, durable_config)
    assert len(checkpoints) == 2

    one = await get_checkpoint(tmp_path, durable_config, "workflow/WorkflowRunner:One")
    assert one is not None
    assert one.get("status") == "completed"


@pytest.mark.asyncio
async def test_durable_overrides_disable_checkpoints(tmp_path: Path) -> None:
    workflow_path = Path(__file__).parent / "flows" / "durable.yml"
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]

    result = await run_workflow(
        workflow=workflow_path,
        output_path=tmp_path,
        workflow_search_paths=workflow_dirs,
        durable_overrides=DurableRunConfig(enabled=False),
    )
    assert result.status == RunnerStatus.COMPLETED
    assert not (tmp_path / ".durable" / "checkpoints.json").exists()
