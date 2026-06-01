"""Tests for workflow execution summary reporter."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunContext, RunnerRegistryKeys, RunnerStatus
from ofx.runner.execution_summary import ExecutionSummaryReporter
from ofx.runner.runner_refs import runner_leaf_descendants
from ofx.runner.workflow import WorkflowRunner


def test_runner_leaf_descendants_skips_none_root():
    assert runner_leaf_descendants(None) == []


def test_runner_leaf_descendants_returns_only_leaf_runners_in_order():
    leaf_a = SimpleNamespace(name="a")
    leaf_b = SimpleNamespace(name="b")
    tree = SimpleNamespace(
        _runners={
            "branch": SimpleNamespace(_runners={"a": leaf_a, "b": leaf_b}),
            "leaf": SimpleNamespace(name="c"),
        }
    )

    leaves = runner_leaf_descendants(tree)

    assert leaves == [leaf_a, leaf_b, tree._runners["leaf"]]


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


@pytest.mark.asyncio
async def test_execution_summary_flattens_matrix_job_children():
    workflow_yaml = """
name: Matrix Summary Workflow
jobs:
  scan:
    strategy:
      matrix:
        target: [a, b, c]
    steps:
      - run: echo "{{ matrix.target }}"
"""
    workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
    runner = WorkflowRunner(workflow, RunContext())

    result = await runner.run()

    assert result.status == RunnerStatus.COMPLETED
    summary = await runner.reg_get(RunnerRegistryKeys.SUMMARY)
    unified = await runner.reg_get(RunnerRegistryKeys.SUMMARY_UNIFIED)

    assert summary is not None
    assert unified is not None
    assert summary["total_jobs"] == 1
    assert summary["failed_jobs"] == 0
    assert summary["total_steps"] == 3
    assert len(summary["jobs"]) == 1
    assert summary["jobs"][0]["jid"] == "scan"
    assert len(unified["jobs"]) == 1
    assert len(unified["jobs"][0]["steps"]) == 3


@pytest.mark.asyncio
async def test_job_summaries_fall_back_to_runner_state_when_result_fails():
    job_runner = SimpleNamespace(
        model=SimpleNamespace(jid="job-1", name="job-1", steps=[object()]),
        status=RunnerStatus.FAILED,
        _error="job boom",
        duration_ms=lambda: 9,
    )

    job_runner.reg_get = AsyncMock(return_value=None)
    workflow_runner = SimpleNamespace(
        model=SimpleNamespace(name="wf"),
        status=RunnerStatus.COMPLETED,
        runners={"job-1": job_runner},
    )
    reporter = ExecutionSummaryReporter(workflow_runner)
    step_runner = SimpleNamespace(
        model=SimpleNamespace(step_index=3, name="step-3"),
        status=RunnerStatus.FAILED,
        _error="boom",
        duration_ms=lambda: 42,
        get_result=lambda: (_ for _ in ()).throw(RuntimeError("no result")),
    )

    with patch(
        "ofx.runner.execution_summary.runner_leaf_descendants",
        return_value=[step_runner],
    ):
        summaries = await reporter._job_summaries()

    assert summaries == [{
        "jid": "job-1",
        "name": "job-1",
        "status": RunnerStatus.FAILED.value,
        "error": "job boom",
        "total_steps": 1,
        "failed_steps": [3],
        "duration_ms": 9,
        "steps": [
        {
            "step_index": 3,
            "name": "step-3",
            "status": RunnerStatus.FAILED.value,
            "error": "boom",
            "duration_ms": 42,
        }
    ]}]


@pytest.mark.asyncio
async def test_build_unified_reuses_workflow_metadata_and_counts():
    workflow_runner = SimpleNamespace(model=SimpleNamespace(name="wf"), status=RunnerStatus.FINISHED)
    reporter = ExecutionSummaryReporter(workflow_runner)

    reporter._job_summaries = AsyncMock(return_value=[{
        "jid": "job-1",
        "status": RunnerStatus.COMPLETED.value,
        "total_steps": 2,
        "failed_steps": [],
    }])

    payload = await reporter.build_unified()

    assert payload == {
        "workflow_name": "wf",
        "status": RunnerStatus.COMPLETED.value,
        "total_jobs": 1,
        "failed_jobs": 0,
        "total_steps": 2,
        "failed_steps": 0,
        "jobs": [
            {
                "jid": "job-1",
                "name": None,
                "status": RunnerStatus.COMPLETED.value,
                "error": None,
                "duration_ms": None,
                "steps": [],
            }
        ],
    }


@pytest.mark.asyncio
async def test_build_and_build_unified_share_loaded_job_summaries():
    workflow_runner = SimpleNamespace(
        model=SimpleNamespace(name="wf"),
        status=RunnerStatus.COMPLETED,
    )
    reporter = ExecutionSummaryReporter(workflow_runner)
    reporter._job_summaries = AsyncMock(return_value=[
        {
            "jid": "job-1",
            "status": RunnerStatus.COMPLETED.value,
            "total_steps": 1,
            "failed_steps": [],
            "steps": [],
        }
    ])

    summary = await reporter.build()
    unified = await reporter.build_unified()

    assert summary.total_jobs == 1
    assert unified["total_jobs"] == 1
    assert reporter._job_summaries.await_count == 1
