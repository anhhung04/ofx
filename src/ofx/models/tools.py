"""Tool installation configuration."""

from typing import Literal

from pydantic import Field

from ofx.models.base import OFXBaseModel


class ToolConfig(OFXBaseModel):
    """Configuration for tool installation and verification.

    Install strategies (checked in order):
      1. ``url`` — download a prebuilt binary/archive (fastest, no package manager)
      2. ``install`` — shell command (apt/go/cargo/npm/uv/…)
    """

    install: str = Field(
        default="",
        description="Command to install the tool (used when no url is set)",
    )
    url: str = Field(
        default="",
        description=(
            "URL of a prebuilt binary or archive to download. "
            "Supports {os}, {arch}, and {version} placeholders."
        ),
    )
    sha256: str = Field(
        default="",
        description="Expected SHA-256 of the downloaded file (empty = skip verification)",
    )
    version: str = Field(
        default="latest",
        description="Version string substituted into the url {version} placeholder",
    )
    archive_path: str = Field(
        default="",
        description=(
            "Path of the binary inside a downloaded archive "
            "(empty = the download is the binary itself)"
        ),
    )
    method: Literal["auto", "binary", "shell"] = Field(
        default="auto",
        description="Force install strategy: 'binary' (url only), 'shell' (install only), or 'auto'",
    )
    check: None | str = Field(
        default=None,
        description="Command to check if tool is already installed (exit 0 = installed)",
    )
    post_install: None | str = Field(
        default=None, description="Command to run after successful installation"
    )
    install_guide: str = Field(
        default="",
        description="Human-readable install instructions shown when auto-install is off",
    )
