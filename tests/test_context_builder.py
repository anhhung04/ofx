"""Tests for public run-context helper functions."""

from ofx.runner import RunContext
from ofx.runner.context import (
    context_copy,
    context_with_env,
    context_with_secrets,
    context_with_update,
    context_with_vars,
)


def test_context_with_env_merges_and_copies():
    base = RunContext(envs={"A": "1"})

    ctx = context_with_env(base, {"B": "2", "A": "override"})

    assert ctx.envs == {"A": "override", "B": "2"}
    assert base.envs == {"A": "1"}


def test_context_with_secrets_merge_without_mutating_base():
    base = RunContext(inputs={"x": 1}, secrets={"token": "a"})

    secrets_ctx = context_with_secrets(base, {"token": "b", "extra": "c"})

    assert secrets_ctx.secrets == {"token": "b", "extra": "c"}
    assert base.inputs == {"x": 1}
    assert base.secrets == {"token": "a"}


def test_context_with_vars_deep_copies_existing_nested_values():
    base = RunContext(vars={"nested": {"list": [1, 2, 3]}})

    ctx = context_with_vars(base, {"extra": "val"})
    ctx.vars["nested"]["list"].append(99)

    assert ctx.vars["extra"] == "val"
    assert 99 not in base.vars["nested"]["list"]

def test_context_with_update_replaces_fields():
    base = RunContext(inputs={"x": 1}, envs={"A": "1"})

    ctx = context_with_update(base, {"inputs": {"z": 9}})

    assert ctx.inputs == {"z": 9}
    assert ctx.envs == {"A": "1"}

def test_context_copy_returns_independent_deep_copy_with_updates():
    base = RunContext(
        inputs={"region": "us-east-1"},
        vars={"nested": {"attempt": 1}},
    )

    copied = context_copy(base, {"inputs": {"tool": "nmap"}}, deep=True)
    copied.vars["nested"]["attempt"] = 2

    assert copied.inputs == {"tool": "nmap"}
    assert base.inputs == {"region": "us-east-1"}
    assert base.vars["nested"]["attempt"] == 1
