"""Tests for the runner factory that selects job runner type."""

from unittest.mock import MagicMock

import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunContext
from ofx.runner.cloud_fleet import CloudFleetRunner
from ofx.runner.cloud_job import CloudJobRunner
from ofx.runner.cloud_matrix import CloudMatrixJobRunner
from ofx.runner.job import JobRunner, MatrixJobRunner
from ofx.runner.runner_factory import job_runner_class


def _job(spec: str):
    wf = Workflow.model_validate(yaml.safe_load(spec))
    return next(iter(wf.jobs.values()))


def test_plain_job_returns_job_runner():
    job = _job("""
name: test
jobs:
  j1:
    steps:
      - run: echo hi
""")
    runner = job_runner_class(job)(job, RunContext(), parent=MagicMock())
    assert isinstance(runner, JobRunner)
    assert job_runner_class(job) is JobRunner


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
    runner = job_runner_class(job)(job, RunContext(), parent=MagicMock())
    assert isinstance(runner, MatrixJobRunner)
    assert job_runner_class(job) is MatrixJobRunner


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
    runner = job_runner_class(job)(job, RunContext(), parent=MagicMock())
    assert isinstance(runner, CloudJobRunner)
    assert job_runner_class(job) is CloudJobRunner


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
    runner = job_runner_class(job)(job, RunContext(), parent=MagicMock())
    assert isinstance(runner, CloudMatrixJobRunner)
    assert job_runner_class(job) is CloudMatrixJobRunner


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
    runner = job_runner_class(job)(job, RunContext(), parent=MagicMock())
    assert isinstance(runner, CloudFleetRunner)
    assert job_runner_class(job) is CloudFleetRunner


def test_runner_factory_class_selection_reflects_job_shape():
    plain = _job("""
name: test
jobs:
  j1:
    steps:
      - run: echo hi
""")
    cloud = _job("""
name: test
jobs:
  j1:
    cloud:
      provider: static
      ssh_host: 1.2.3.4
    steps:
      - run: echo hi
""")
    matrix = _job("""
name: test
jobs:
  j1:
    strategy:
      matrix:
        target: [a, b]
    steps:
      - run: echo hi
""")
    fleet = _job("""
name: test
jobs:
  j1:
    strategy:
      fleet:
        count: 2
        input: "1.1.1.1"
    steps:
      - run: echo hi
""")

    assert job_runner_class(plain) is JobRunner
    assert job_runner_class(cloud) is CloudJobRunner
    assert job_runner_class(matrix) is MatrixJobRunner
    assert job_runner_class(fleet) is JobRunner
