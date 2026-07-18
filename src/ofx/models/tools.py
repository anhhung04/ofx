"""Tool installation configuration."""

from pydantic import Field

from ofx.models.base import OFXBaseModel

class ToolConfig(OFXBaseModel):
    """Configuration for tool installation and verification."""

    install: str = Field(..., description="Command to install the tool")
    check: None | str = Field(
        default=None,
        description="Command to check if tool is already installed (exit 0 = installed)",
    )
    post_install: None | str = Field(
        default=None, description="Command to run after successful installation"
    )
