"""Parity tests for the kwargs shim embedded in remote UDF wrapper sources.

The generated ``ofx.api`` wrapper cannot import
:func:`ofx.modules.api.invoke_api_callable` (module bundles only collect
``ofx.api.*`` sources), so it carries :data:`ofx.cloud.udf_wrapper.
INVOKE_KWARGS_SHIM` — a single canonical constant. These tests execute that
shim and assert it behaves like the real implementation: same argument
filtering, same ``**kwargs`` passthrough, same failure on missing required
parameters.
"""

from __future__ import annotations

import pytest

from ofx.cloud.udf_wrapper import INVOKE_KWARGS_SHIM, build_udf_step_source
from ofx.models.step import Step
from ofx.modules.api import ApiModuleError, invoke_api_callable


def _load_shim():
    """Execute the shim constant and return its ``_invoke_kwargs``.

    The wrapper imports ``inspect as _inspect``; supply the same binding so
    the shim can be exercised standalone.
    """
    import inspect

    namespace: dict[str, object] = {"_inspect": inspect}
    exec(compile(INVOKE_KWARGS_SHIM, "<shim>", "exec"), namespace)
    return namespace["_invoke_kwargs"]


def _raises(func, *args, **kwargs) -> BaseException:
    """Return the exception raised by calling *func*."""
    try:
        func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - test helper
        return exc
    raise AssertionError("expected an exception")


def _required(a, b):  # pragma: no cover - used via signature inspection
    return a, b


def _with_defaults(a, b=2):  # pragma: no cover - used via signature inspection
    return a, b


def _with_kwargs(a, **rest):  # pragma: no cover - used via signature inspection
    return a, rest


@pytest.fixture(scope="module")
def shim():
    return _load_shim()


def test_shim_filters_unknown_keys_like_invoke_api_callable(shim):
    args = {"a": "x", "b": "y", "unrelated": "ignored"}
    assert shim(_required, args) == invoke_api_callable(_required, args) == ("x", "y")


def test_shim_fills_defaults_like_invoke_api_callable(shim):
    args = {"a": "x", "b": "ignored", "other": 1}
    assert shim(_with_defaults, {"a": "x", "other": 1}) == invoke_api_callable(
        _with_defaults, {"a": "x", "other": 1}
    )
    assert shim(_with_defaults, args) == invoke_api_callable(_with_defaults, args)


def test_shim_passes_everything_through_for_kwargs_functions(shim):
    args = {"a": 1, "extra": "kept"}
    assert shim(_with_kwargs, args) == invoke_api_callable(_with_kwargs, args)


def test_shim_and_invoke_api_callable_agree_on_missing_argument(shim):
    args = {"unrelated": "x"}
    shim_error = _raises(shim, _required, args)
    real_error = _raises(invoke_api_callable, _required, args)

    assert isinstance(real_error, ApiModuleError)
    assert isinstance(shim_error, TypeError)
    for exc in (shim_error, real_error):
        message = str(exc)
        assert "missing required argument" in message.lower()
        assert "b" in message
        assert "unrelated" in message


def test_generated_api_wrapper_embeds_the_canonical_shim(tmp_path):
    step = Step(name="api-step", module="local.api.strings.remove_duplicate_string")
    wrapper = build_udf_step_source(
        step,
        workflow_dir=tmp_path,
        inputs={"strings": ["a", "a"]},
        secrets={},
    )
    assert INVOKE_KWARGS_SHIM in wrapper
    assert "def _invoke_kwargs(_func, _args):" in wrapper
