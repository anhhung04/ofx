"""Tests for run_if conditions across jobs and steps."""

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner.core import RunContext, RunnerStatus
from ofx.runner.execution.workflow import WorkflowRunner


class TestRunIfConditions:
    @pytest.mark.asyncio
    async def test_job_runs_on_failure_dependency(self):
        workflow_yaml = """
name: RunIf Failure Workflow
jobs:
  fail_job:
    steps:
      - run: exit 1
  on_failure:
    needs: [fail_job]
    run_if: failure()
    steps:
      - run: echo "ran on failure"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())
        result = await runner.run()

        assert result.status == RunnerStatus.FAILED
        assert "fail_job" in runner.runners
        assert "on_failure" in runner.runners
        assert runner.runners["on_failure"].status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_step_run_if_false_is_canceled(self):
        workflow_yaml = """
name: RunIf Step Canceled
jobs:
  test_job:
    steps:
      - run: echo "skip"
        run_if: false
      - run: echo "next"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        job_runner = runner.runners["test_job"]
        step0 = job_runner._runners["0"]
        step1 = job_runner._runners["1"]
        assert step0.status == RunnerStatus.CANCELED
        assert step1.status == RunnerStatus.COMPLETED
