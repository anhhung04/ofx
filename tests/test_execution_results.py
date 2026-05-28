"""Tests for structured execution results on job and step runners."""

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.workflow import WorkflowRunner


@pytest.mark.asyncio
async def test_job_and_step_execution_results():
    workflow_yaml = """
name: Exec Results
jobs:
  test_job:
    steps:
      - run: echo "ok"
      - run: echo "ok2"
"""
    workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
    runner = WorkflowRunner(workflow, RunContext())
    result = await runner.run()

    assert result.status == RunnerStatus.COMPLETED
    job_runner = runner.runners["test_job"]

    job_exec = await job_runner.reg_get("execution")
    assert job_exec is not None
    assert job_exec["jid"] == "test_job"
    assert job_exec["total_steps"] == 2
    assert job_exec["failed_steps"] == []
    assert len(job_exec["steps"]) == 2

    step0 = job_runner._runners["0"]
    step_exec = await step0.reg_get("execution")
    assert step_exec is not None
    assert step_exec["step_index"] == 0
    assert step_exec["status"] == RunnerStatus.COMPLETED.value
