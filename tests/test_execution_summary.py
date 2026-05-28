"""Tests for workflow execution summary reporter."""

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunContext, RunnerRegistryKeys, RunnerStatus
from ofx.runner.workflow import WorkflowRunner


@pytest.mark.asyncio
async def test_execution_summary_contains_job_and_step_counts():
    workflow_yaml = """
name: Summary Workflow
jobs:
  job1:
    steps:
      - run: echo "ok"
      - run: echo "ok2"
  job2:
    steps:
      - run: exit 1
      - run: echo "ok3"
        run_if: failure()
"""
    workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
    runner = WorkflowRunner(workflow, RunContext())
    result = await runner.run()

    assert result.status == RunnerStatus.FAILED
    summary = await runner.reg_get(RunnerRegistryKeys.SUMMARY)
    unified = await runner.reg_get(RunnerRegistryKeys.SUMMARY_UNIFIED)
    assert summary is not None
    assert unified is not None
    assert summary["workflow_name"] == "Summary Workflow"
    assert summary["total_jobs"] == 2
    assert summary["failed_jobs"] == 1
    assert summary["total_steps"] == 4
    assert summary["failed_steps"] >= 1
    assert len(summary["jobs"]) == 2
    assert len(unified["jobs"]) == 2
    assert unified["total_steps"] == 4
