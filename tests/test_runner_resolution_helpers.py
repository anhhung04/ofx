from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from ofx.runner import RunContext, Runner


class _TemplateModel(BaseModel):
    name: str = "wf"
    outputs: dict[str, str] = {}


class _TemplateRunner(Runner[_TemplateModel]):
    async def _pre_run(self) -> None: ...
    async def _do_run(self) -> None: ...
    async def _post_run(self) -> None: ...


@pytest.mark.asyncio
async def test_resolve_job_outputs_logs_and_falls_back_on_error() -> None:
    runner = _TemplateRunner(_TemplateModel(outputs={"target": "{{ bad }}"}), RunContext())
    warnings: list[str] = []
    runner._log_warning = warnings.append

    async def _resolve_template(_value):
        raise RuntimeError("boom")

    runner._resolve_template = _resolve_template

    value = await runner._resolve_job_outputs()

    assert value == {"target": ""}
    assert warnings == ["Failed to resolve output 'target': boom"]


@pytest.mark.asyncio
async def test_resolve_template_fields_filters_missing_attributes() -> None:
    runner = _TemplateRunner(_TemplateModel(name="wf"), RunContext())

    async def _resolve_template(value):
        return f"resolved:{value}"

    runner._resolve_template = _resolve_template

    changed = await runner._resolve_template_fields(["name", "missing"])

    assert changed is True
    assert runner.model.name == "resolved:wf"


@pytest.mark.asyncio
async def test_resolve_template_fields_returns_false_when_all_fields_are_missing() -> None:
    runner = _TemplateRunner(_TemplateModel(name="wf"), RunContext())

    assert await runner._resolve_template_fields(["missing"]) is False
    assert runner.model.name == "wf"


@pytest.mark.asyncio
async def test_resolve_job_outputs_uses_shared_resolution() -> None:
    runner = _TemplateRunner(_TemplateModel(outputs={"a": "x", "b": "y"}), RunContext())
    runner.model = SimpleNamespace(outputs={"a": "x", "b": "y"})

    async def _resolve_template(value):
        return f"resolved:{value}"

    runner._resolve_template = _resolve_template

    assert await runner._resolve_job_outputs() == {
        "a": "resolved:x",
        "b": "resolved:y",
    }
