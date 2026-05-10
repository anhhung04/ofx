"""RunContext builder helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ofx.runner.core.models import RunContext


@dataclass(frozen=True)
class RunnerContextBuilder:
    base: RunContext

    def _shallow_copy_with_dict(self, field: str, updates: dict[str, Any]) -> RunContext:
        """Create a copy of base, deep-copying only the target dict field."""
        import copy

        # Deep-copy the target dict so nested structures are isolated
        current = copy.deepcopy(getattr(self.base, field))
        current.update(updates)
        return self.base.model_copy(update={field: current})

    def with_env(self, env: dict[str, Any]) -> RunContext:
        return self._shallow_copy_with_dict("envs", env)

    def with_inputs(self, inputs: dict[str, Any]) -> RunContext:
        return self._shallow_copy_with_dict("inputs", inputs)

    def with_secrets(self, secrets: dict[str, Any]) -> RunContext:
        return self._shallow_copy_with_dict("secrets", secrets)

    def with_vars(self, vars_update: dict[str, Any]) -> RunContext:
        return self._shallow_copy_with_dict("vars", vars_update)

    def with_update(self, update: dict[str, Any]) -> RunContext:
        return self.base.model_copy(update=update)
