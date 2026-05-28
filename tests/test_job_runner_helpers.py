"""Tests for shared job runner helper functions."""

from __future__ import annotations

from ofx.models.job import Job
from ofx.runner.job import clone_indexed_job


def _job() -> Job:
    return Job(
        jid="scan",
        name="scan job",
        steps=[{"run": "echo hi"}],
        env={"MODE": "base"},
    )


def test_clone_indexed_job_sets_child_identity_and_matrix_metadata():
    job = _job()

    cloned = clone_indexed_job(
        job,
        2,
        {"tool": "nmap"},
        display_name="[scan]{2}",
    )

    assert cloned.name == "[scan]{2}"
    assert cloned.jid == "scan_2"
    assert cloned.matrix_values == {"tool": "nmap"}
    assert cloned.matrix_index == 2


def test_clone_indexed_job_builds_default_display_name_from_job_name():
    job = _job()

    cloned = clone_indexed_job(
        job,
        3,
        {"tool": "naabu"},
    )

    assert cloned.name == "[scan job]{3}"
    assert cloned.jid == "scan_3"


def test_clone_indexed_job_is_deep_copy():
    job = _job()

    cloned = clone_indexed_job(
        job,
        1,
        {"tool": "httpx"},
        display_name="[scan]{1}",
    )
    cloned.env["MODE"] = "child"

    assert job.env["MODE"] == "base"
