"""Tests for local job runner log formatting helpers."""

from __future__ import annotations

from ofx.models.job import Job
from ofx.runner.job import JobRunner, MatrixJobRunner
from ofx.runner.logging import bubble_context_log


class ParentStub:
    def __init__(self) -> None:
        self.received: str | None = None

    def _produce_log(self, message: str) -> str:
        self.received = message
        return f"parent::{message}"

def test_job_log_bubbles_prefixed_message_to_parent():
    parent = ParentStub()

    result = bubble_context_log(
        parent,
        "hello",
        model_jid=Job(jid="job-1", steps=[{"run": "echo hi"}]).jid,
    )

    assert parent.received == "job=job-1 › hello"
    assert result == "parent::job=job-1 › hello"


def test_job_and_matrix_runners_share_job_log_formatting():
    parent = ParentStub()
    job = Job(jid="build", steps=[{"run": "echo hi"}])

    job_runner = object.__new__(JobRunner)
    job_runner.model = job
    job_runner.parent = parent

    matrix_runner = object.__new__(MatrixJobRunner)
    matrix_runner.model = job
    matrix_runner.parent = parent

    assert job_runner._produce_log("done") == "parent::job=build › done"
    assert matrix_runner._produce_log("done") == "parent::job=build › done"
