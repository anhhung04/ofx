"""Test parallel job execution in workflows."""

import time
from pathlib import Path

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunnerManager


@pytest.mark.asyncio
async def test_parallel_jobs_execution():
    """Test that jobs without dependencies run in parallel."""
    # Create a test workflow with 3 jobs, each taking 2 seconds
    workflow_content = """
name: Parallel Test
jobs:
  job1:
    steps:
      - run: sleep 2
  job2:
    steps:
      - run: sleep 2
  job3:
    steps:
      - run: sleep 2
"""

    workflow = Workflow.model_validate(yaml.safe_load(workflow_content))

    start = time.time()
    result = await RunnerManager.run_workflow(
        workflow, output_path=Path("/tmp/ofx-parallel-test")
    )
    elapsed = time.time() - start

    # If running in parallel, should take ~2 seconds
    # If running sequentially, would take ~6 seconds
    # Allow some overhead, so check it's less than 4 seconds
    assert elapsed < 4.0, (
        f"Jobs took {elapsed:.2f}s, expected < 4s (parallel execution)"
    )
    assert elapsed > 1.5, f"Jobs took {elapsed:.2f}s, seems too fast"
    assert result.status.value == "completed"


@pytest.mark.asyncio
async def test_sequential_jobs_with_dependencies():
    """Test that jobs with dependencies run sequentially."""
    workflow_content = """
name: Sequential Test
jobs:
  job1:
    steps:
      - run: sleep 1
  job2:
    needs: job1
    steps:
      - run: sleep 1
  job3:
    needs: job2
    steps:
      - run: sleep 1
"""

    workflow = Workflow.model_validate(yaml.safe_load(workflow_content))

    start = time.time()
    result = await RunnerManager.run_workflow(
        workflow, output_path=Path("/tmp/ofx-sequential-test")
    )
    elapsed = time.time() - start

    # Should take ~3 seconds since they run sequentially
    assert elapsed > 2.5, f"Jobs took {elapsed:.2f}s, expected > 2.5s (sequential)"
    assert elapsed < 5.0, f"Jobs took {elapsed:.2f}s, expected < 5s"
    assert result.status.value == "completed"


@pytest.mark.asyncio
async def test_mixed_parallel_sequential():
    """Test workflow with both parallel and sequential execution."""
    workflow_content = """
name: Mixed Test
jobs:
  job1:
    steps:
      - run: sleep 1
  job2:
    steps:
      - run: sleep 1
  job3:
    needs: [job1, job2]
    steps:
      - run: sleep 1
"""

    workflow = Workflow.model_validate(yaml.safe_load(workflow_content))

    start = time.time()
    result = await RunnerManager.run_workflow(
        workflow, output_path=Path("/tmp/ofx-mixed-test")
    )
    elapsed = time.time() - start

    # job1 and job2 run in parallel (1s), then job3 runs (1s)
    # Total should be ~2 seconds
    assert elapsed > 1.5, f"Jobs took {elapsed:.2f}s, expected > 1.5s"
    assert elapsed < 3.5, f"Jobs took {elapsed:.2f}s, expected < 3.5s"
    assert result.status.value == "completed"
