"""Pipe (ETL) configuration model for declarative data transformation between steps."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from ofx.models.base import OFXBaseModel


class PipeConfig(OFXBaseModel):
    """Declarative ETL pipeline executed as a step.

    Operations are applied in order:
      input → filter → map → flatten → sort → unique → group_by → offset → limit → format
    """

    input: str = Field(
        ...,
        description=(
            "Jinja2 expression that resolves to a list of items. "
            "Example: '{{ steps.scan.outputs.typed_outputs | ports }}'"
        ),
    )

    filter: str | None = Field(
        default=None,
        description=(
            "Python expression evaluated per item. Item fields are available "
            "as local variables.  Example: \"state == 'open' and port > 1000\""
        ),
    )

    map: dict[str, str] | None = Field(
        default=None,
        description=(
            "Dict of field_name → Python expression. Produces new objects "
            "with only the mapped fields.  Example: {url: \"'http://' + host\"}"
        ),
    )

    flatten: str | None = Field(
        default=None,
        description="Flatten a nested list field. The named field is expanded in-place.",
    )

    sort: str | list[str] | None = Field(
        default=None,
        description="Sort by field name(s). String or list of strings.",
    )
    reverse: bool = Field(default=False, description="Reverse the sort order.")

    unique: str | list[str] | None = Field(
        default=None,
        description="Deduplicate by field name(s). First occurrence wins.",
    )

    group_by: str | None = Field(
        default=None,
        alias="group-by",
        description="Group items by a field. Output becomes a dict of lists.",
    )

    limit: int | None = Field(
        default=None, ge=1, description="Maximum number of items to keep."
    )
    offset: int | None = Field(
        default=None, ge=0, description="Skip the first N items."
    )

    format: Literal["json", "jsonl", "lines", "csv", "yaml"] = Field(
        default="json",
        description="Output serialization format written to the temp file.",
    )
    field: str | None = Field(
        default=None,
        description=(
            "For 'lines' format, extract this field from each item. "
            "For scalar lists (strings/ints) this is ignored."
        ),
    )
    separator: str = Field(
        default="\n",
        description="Line separator for 'lines' format.",
    )
    headers: bool = Field(
        default=True,
        description="Include header row in 'csv' format.",
    )

    @model_validator(mode="after")
    def _validate_config(self) -> PipeConfig:
        if self.format == "lines" and self.group_by:
            raise ValueError(
                "Cannot combine format='lines' with group-by; "
                "use 'json' or 'jsonl' for grouped output."
            )
        if self.limit is not None and self.limit < 1:
            raise ValueError("limit must be >= 1")
        return self
