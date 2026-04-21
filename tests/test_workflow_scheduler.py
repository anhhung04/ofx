"""Tests for workflow scheduling: topological sort, parallel stages, cycles."""

from __future__ import annotations

import pytest

from ofx.utils.scheduling import find_parallel_schedule

# ── find_parallel_schedule ───────────────────────────────────────────────


class TestFindParallelSchedule:
    """Topological sort that groups independent jobs into parallel stages."""

    def test_single_job(self):
        schedule = find_parallel_schedule(["a"], [])
        assert schedule == [["a"]]

    def test_two_independent_jobs(self):
        schedule = find_parallel_schedule(["a", "b"], [])
        assert len(schedule) == 1
        assert set(schedule[0]) == {"a", "b"}

    def test_two_sequential_jobs(self):
        schedule = find_parallel_schedule(["a", "b"], [("a", "b")])
        assert schedule == [["a"], ["b"]]

    def test_diamond_dependency(self):
        # a → b, a → c, b → d, c → d
        jobs = ["a", "b", "c", "d"]
        deps = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]
        schedule = find_parallel_schedule(jobs, deps)
        assert len(schedule) == 3
        assert schedule[0] == ["a"]
        assert set(schedule[1]) == {"b", "c"}
        assert schedule[2] == ["d"]

    def test_three_stages(self):
        # a → b → c, a → d (d parallel with b)
        jobs = ["a", "b", "c", "d"]
        deps = [("a", "b"), ("b", "c"), ("a", "d")]
        schedule = find_parallel_schedule(jobs, deps)
        assert schedule[0] == ["a"]
        assert set(schedule[1]) == {"b", "d"}
        assert schedule[2] == ["c"]

    def test_circular_dependency_raises(self):
        with pytest.raises(ValueError, match="circular dependency"):
            find_parallel_schedule(["a", "b"], [("a", "b"), ("b", "a")])

    def test_self_referencing_raises(self):
        with pytest.raises(ValueError, match="circular dependency"):
            find_parallel_schedule(["a"], [("a", "a")])

    def test_three_node_cycle_raises(self):
        deps = [("a", "b"), ("b", "c"), ("c", "a")]
        with pytest.raises(ValueError, match="circular dependency"):
            find_parallel_schedule(["a", "b", "c"], deps)

    def test_unknown_dependency_ignored(self):
        # Dependency on a job not in the list is ignored
        schedule = find_parallel_schedule(["a", "b"], [("x", "b")])
        # Both are independent since x doesn't exist
        assert len(schedule) == 1
        assert set(schedule[0]) == {"a", "b"}

    def test_empty_jobs(self):
        schedule = find_parallel_schedule([], [])
        assert schedule == []

    def test_many_independent_jobs(self):
        jobs = [f"job_{i}" for i in range(20)]
        schedule = find_parallel_schedule(jobs, [])
        assert len(schedule) == 1
        assert len(schedule[0]) == 20

    def test_linear_chain(self):
        # a → b → c → d → e
        jobs = ["a", "b", "c", "d", "e"]
        deps = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")]
        schedule = find_parallel_schedule(jobs, deps)
        assert len(schedule) == 5
        for i, stage in enumerate(schedule):
            assert stage == [jobs[i]]


# ── WorkflowScheduler ───────────────────────────────────────────────────


class TestWorkflowScheduler:
    """Tests for the WorkflowScheduler wrapper."""

    def _make_job(self, needs: list[str] | None = None):
        from ofx.models.job import Job
        from ofx.models.step import Step

        return Job(
            steps=[Step(run="echo test")],
            needs=needs or [],
        )

    def test_plan_no_deps(self):
        from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

        jobs = {"a": self._make_job(), "b": self._make_job()}
        ws = WorkflowScheduler(jobs)
        result = ws.plan()
        assert len(result.schedule) == 1
        assert set(result.schedule[0]) == {"a", "b"}
        assert result.staged_jobs is jobs

    def test_plan_with_deps(self):
        from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

        jobs = {
            "build": self._make_job(),
            "test": self._make_job(needs=["build"]),
            "deploy": self._make_job(needs=["test"]),
        }
        ws = WorkflowScheduler(jobs)
        result = ws.plan()
        assert len(result.schedule) == 3
        assert result.schedule[0] == ["build"]
        assert result.schedule[1] == ["test"]
        assert result.schedule[2] == ["deploy"]

    def test_dependencies_static_method(self):
        from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

        jobs = {
            "a": self._make_job(),
            "b": self._make_job(needs=["a"]),
        }
        deps = WorkflowScheduler.dependencies(jobs)
        assert ("a", "b") in deps

    def test_job_ids_static_method(self):
        from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

        jobs = {"x": self._make_job(), "y": self._make_job()}
        ids = list(WorkflowScheduler.job_ids(jobs))
        assert set(ids) == {"x", "y"}
