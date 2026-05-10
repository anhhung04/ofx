"""Tests for the runner factory that selects job runner type."""

from unittest.mock import MagicMock

import yaml

from ofx.models.workflow import Workflow
from ofx.runner.core import RunContext
from ofx.runner.execution.cloud_fleet import CloudFleetRunner
from ofx.runner.execution.cloud_job import CloudJobRunner
from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner
from ofx.runner.execution.job import JobRunner, MatrixJobRunner
from ofx.runner.execution.runner_factory import create_job_runner


def _job(spec: str):
    wf = Workflow.model_validate(yaml.safe_load(spec))
    return next(iter(wf.jobs.values()))


def _ctx():
    return RunContext()


def _parent():
    return MagicMock()


def test_plain_job_returns_job_runner():
    job = _job("""
name: test
jobs:
  j1:
    steps:
      - run: echo hi
""")
    runner = create_job_runner(job, _ctx(), _parent())
    assert isinstance(runner, JobRunner)


def test_matrix_job_returns_matrix_job_runner():
    job = _job("""
name: test
jobs:
  j1:
    strategy:
      matrix:
        target: [a, b]
    steps:
      - run: echo hi
""")
    runner = create_job_runner(job, _ctx(), _parent())
    assert isinstance(runner, MatrixJobRunner)


def test_cloud_job_returns_cloud_job_runner():
    job = _job("""
name: test
jobs:
  j1:
    cloud:
      provider: static
      ssh_host: 1.2.3.4
    steps:
      - run: echo hi
""")
    runner = create_job_runner(job, _ctx(), _parent())
    assert isinstance(runner, CloudJobRunner)


def test_cloud_matrix_returns_cloud_matrix_job_runner():
    job = _job("""
name: test
jobs:
  j1:
    cloud:
      provider: static
      ssh_host: 1.2.3.4
    strategy:
      matrix:
        target: [a, b]
    steps:
      - run: echo hi
""")
    runner = create_job_runner(job, _ctx(), _parent())
    assert isinstance(runner, CloudMatrixJobRunner)


def test_cloud_fleet_returns_cloud_fleet_runner():
    job = _job("""
name: test
jobs:
  j1:
    cloud:
      provider: static
      ssh_host: 1.2.3.4
    strategy:
      fleet:
        count: 2
        input: "1.1.1.1\\n2.2.2.2"
    steps:
      - run: echo hi
""")
    runner = create_job_runner(job, _ctx(), _parent())
    assert isinstance(runner, CloudFleetRunner)
