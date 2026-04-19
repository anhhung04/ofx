"""Tests for RunnerContextBuilder context merging behavior."""

import pytest

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


# ── Edge cases ───────────────────────────────────────────────────────────


def test_with_env_empty_dict():
    """Empty update should return a copy without changes."""
    base = RunContext(envs={"A": "1"})
    builder = RunnerContextBuilder(base)
    ctx = builder.with_env({})
    assert ctx.envs["A"] == "1"
    assert ctx is not base


def test_with_vars_empty_dict():
    base = RunContext(vars={"k": "v"})
    builder = RunnerContextBuilder(base)
    ctx = builder.with_vars({})
    assert ctx.vars["k"] == "v"


def test_chained_builders():
    """Multiple builder calls can be chained on successive contexts."""
    base = RunContext()
    b = RunnerContextBuilder(base)
    ctx1 = b.with_env({"A": "1"})
    ctx2 = RunnerContextBuilder(ctx1).with_inputs({"x": 42})
    ctx3 = RunnerContextBuilder(ctx2).with_vars({"role": "scan"})

    assert ctx3.envs["A"] == "1"
    assert ctx3.inputs["x"] == 42
    assert ctx3.vars["role"] == "scan"
    # Original untouched
    assert "A" not in base.envs or base.envs.get("A") != "1"


def test_deep_copy_isolation():
    """Modifying a nested dict in the derived context shouldn't affect the base."""
    base = RunContext(vars={"nested": {"list": [1, 2, 3]}})
    builder = RunnerContextBuilder(base)
    ctx = builder.with_vars({"extra": "val"})
    ctx.vars["nested"]["list"].append(99)

    assert 99 not in base.vars["nested"]["list"]


def test_frozen_builder():
    """RunnerContextBuilder is frozen — attributes can't be reassigned."""
    from dataclasses import FrozenInstanceError

    base = RunContext()
    builder = RunnerContextBuilder(base)
    with pytest.raises(FrozenInstanceError):
        builder.base = RunContext()  # type: ignore[misc]
