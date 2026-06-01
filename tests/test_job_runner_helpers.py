"""Tests for shared job runner helper functions."""

from __future__ import annotations

from types import SimpleNamespace

from ofx.models.job import Job
from ofx.runner import RunContext
from ofx.runner.job import (
    attach_indexed_job_runner,
    build_indexed_job_context,
)


def _job() -> Job:
    return Job(
        jid="scan",
        name="scan job",
        steps=[{"run": "echo hi"}],
        env={"MODE": "base"},
    )


def test_build_indexed_job_context_merges_strategy_vars_and_inputs():
    runner = SimpleNamespace(
        ctx=RunContext(vars={"_matrix_input_keys": ["target"]}),
        model=SimpleNamespace(
            strategy=SimpleNamespace(model_dump=lambda: {"matrix": {"target": ["a"]}})
        ),
        _child_context=lambda: RunContext(vars={"base": "keep"}),
    )

    ctx = build_indexed_job_context(
        runner,
        vars_update={"matrix": {"target": "a"}},
        input_updates={"target": "a"},
    )

    assert ctx.vars["base"] == "keep"
    assert ctx.vars["matrix"] == {"target": "a"}
    assert ctx.vars["strategy"] == {"matrix": {"target": ["a"]}}
    assert ctx.inputs["target"] == "a"


def test_attach_indexed_job_runner_registers_child_on_parent_runner():
    job = _job()
    ctx = RunContext()
    workflow_parent = object()
    runner = SimpleNamespace(
        model=job,
        parent=workflow_parent,
        _runners={},
    )

    job_copy, child_runner = attach_indexed_job_runner(
        runner,
        ctx=ctx,
        index=1,
        values={"tool": "httpx"},
        runner_cls=lambda job_copy, ctx_arg, *, parent, flag=False: SimpleNamespace(
            model=job_copy,
            ctx=ctx_arg,
            parent=parent,
            flag=flag,
        ),
        flag=True,
    )

    assert runner._runners[job_copy.jid] is child_runner
    assert job_copy.name == "[scan job]{1}"
    assert job_copy.jid == "scan_1"
    assert job_copy.matrix_values == {"tool": "httpx"}
    assert job_copy.matrix_index == 1
    assert child_runner.parent is workflow_parent
    assert child_runner.flag is True
    child_runner.model.env["MODE"] = "child"
    assert job.env["MODE"] == "base"


def test_attach_indexed_job_runner_honors_override_parent_and_display_name():
    runner = SimpleNamespace(
        model=_job(),
        parent=object(),
        _runners={},
    )
    ctx = RunContext()
    override_parent = object()

    job_copy, child_runner = attach_indexed_job_runner(
        runner,
        ctx=ctx,
        index=4,
        values={"tool": "nmap"},
        runner_cls=lambda job_copy, ctx_arg, *, parent: SimpleNamespace(
            model=job_copy,
            ctx=ctx_arg,
            parent=parent,
        ),
        parent=override_parent,
        display_name="custom",
    )

    assert job_copy.jid == "scan_4"
    assert job_copy.name == "custom"
    assert job_copy.matrix_values == {"tool": "nmap"}
    assert job_copy.matrix_index == 4
    assert child_runner.model is job_copy
    assert child_runner.ctx is ctx
    assert child_runner.parent is override_parent
