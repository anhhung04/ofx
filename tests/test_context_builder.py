"""Tests for RunnerContextBuilder context merging behavior."""

from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import RunContext


def test_with_env_merges_and_copies():
    base = RunContext(envs={"A": "1"})
    builder = RunnerContextBuilder(base)
    ctx = builder.with_env({"B": "2", "A": "override"})

    assert ctx.envs["A"] == "override"
    assert ctx.envs["B"] == "2"
    assert base.envs["A"] == "1"


def test_with_inputs_merges_and_copies():
    base = RunContext(inputs={"x": 1})
    builder = RunnerContextBuilder(base)
    ctx = builder.with_inputs({"y": 2, "x": 3})

    assert ctx.inputs == {"x": 3, "y": 2}
    assert base.inputs == {"x": 1}


def test_with_secrets_merges_and_copies():
    base = RunContext(secrets={"token": "a"})
    builder = RunnerContextBuilder(base)
    ctx = builder.with_secrets({"token": "b", "extra": "c"})

    assert ctx.secrets == {"token": "b", "extra": "c"}
    assert base.secrets == {"token": "a"}


def test_with_vars_merges_and_copies():
    base = RunContext(vars={"nested": {"k": "v"}})
    builder = RunnerContextBuilder(base)
    ctx = builder.with_vars({"nested": {"k": "v2"}, "m": 1})

    assert ctx.vars["nested"]["k"] == "v2"
    assert ctx.vars["m"] == 1
    assert base.vars["nested"]["k"] == "v"


def test_with_update_replaces_fields():
    base = RunContext(inputs={"x": 1}, envs={"A": "1"})
    builder = RunnerContextBuilder(base)
    ctx = builder.with_update({"inputs": {"z": 9}})

    assert ctx.inputs == {"z": 9}
    assert ctx.envs["A"] == "1"
