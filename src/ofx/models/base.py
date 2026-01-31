"""Base model for all OFX models."""

from pydantic import BaseModel, ConfigDict


class OFXBaseModel(BaseModel):
    """Base model with shared configuration for all OFX models."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )
