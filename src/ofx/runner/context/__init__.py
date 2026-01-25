"""RunContext builder helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ofx.runner.core.models import RunContext


@dataclass(frozen=True)
class RunnerContextBuilder:
    base: RunContext

    def with_env(self, env: dict[str, Any]) -> RunContext:
        ctx = self.base.model_copy(deep=True)
        ctx.envs.update(env)
        return ctx

    def with_inputs(self, inputs: dict[str, Any]) -> RunContext:
        ctx = self.base.model_copy(deep=True)
        ctx.inputs.update(inputs)
        return ctx

    def with_secrets(self, secrets: dict[str, Any]) -> RunContext:
        ctx = self.base.model_copy(deep=True)
        ctx.secrets.update(secrets)
        return ctx

    def with_vars(self, vars_update: dict[str, Any]) -> RunContext:
        ctx = self.base.model_copy(deep=True)
        ctx.vars.update(vars_update)
        return ctx

    def with_update(self, update: dict[str, Any]) -> RunContext:
        return self.base.model_copy(update=update, deep=True)
