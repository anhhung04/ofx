"""Workflow input and secret definitions."""

import re
from typing import Any, Literal

from pydantic import Field, model_validator

from ofx.models.base import OFXBaseModel


class WorkflowInput(OFXBaseModel):
    """Input parameter definition for workflows."""

    required: bool = Field(default=False, description="Whether the input is required")
    default: Any = Field(
        default=None, description="Default value for the input parameter"
    )
    type: Literal["string", "number", "array", "object", "boolean"] = Field(
        default="string",
        description="Type of the input parameter (e.g., 'string', 'number')",
    )
    description: str = Field(
        default="",
        description="Human-readable description of the input parameter",
    )
    alias: str | list[str] | None = Field(
        default=None,
        description="Alias for the input parameter, used for mapping in workflow calls",
    )

    @model_validator(mode="after")
    def validate_alias(self):
        if self.alias is not None:
            if isinstance(self.alias, str):
                if not re.match(r"^[a-zA-Z0-9_-]+$", self.alias):
                    raise ValueError(
                        f"Alias '{self.alias}' does not have a valid pattern. Use letters, numbers, hyphens, and underscores."
                    )
            elif isinstance(self.alias, list):
                for alias in self.alias:
                    if not re.match(r"^[a-zA-Z0-9_-]+$", alias):
                        raise ValueError(
                            f"Alias '{alias}' does not have a valid pattern. Use letters, numbers, hyphens, and underscores."
                        )
            else:
                raise ValueError("Alias must be a string or a list of strings.")
        return self


class WorkflowSecret(OFXBaseModel):
    """Secret parameter definition for workflows."""

    required: bool = Field(default=False, description="Whether the secret is required")
    type: Literal["string", "number", "array", "object", "boolean"] = Field(
        "string", description="Type of the secret (e.g., 'string', 'number')"
    )
