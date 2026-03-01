"""Cloud configuration models for workflow execution on cloud VPS."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from ofx.models.base import OFXBaseModel

# FleetStrategy is defined in strategy.py to avoid circular imports.
# Re-export for convenience.
from ofx.models.strategy import FleetStrategy


class CloudHostEntry(OFXBaseModel):
    """A single static host entry for fleet usage."""

    host: str = Field(..., description="Hostname or IP address")
    ssh_user: str = Field(default="root", description="SSH username for this host")
    ssh_port: int = Field(default=22, description="SSH port for this host")
    ssh_key: str = Field(default="", description="Override SSH key for this host")
    ssh_password: str = Field(default="", description="Override SSH password for this host")


class CloudConfig(OFXBaseModel):
    """Cloud configuration for running a job on a cloud VPS or existing host.

    Can be specified as a string (profile slug) or an object with full config.
    When specified as a string, the profile is loaded from ~/.ofx/cloud.yml.
    """

    model_config = {**OFXBaseModel.model_config, "extra": "allow"}

    # Profile reference
    profile: str = Field(
        default="",
        description="Reference to a named profile in ~/.ofx/cloud.yml",
    )

    # Provider
    provider: str = Field(
        default="",
        description="Cloud provider: digitalocean, aws, or static",
    )

    # Instance spec (ignored for static provider)
    region: str = Field(default="", description="Cloud region (e.g., nyc3, us-east-1)")
    size: str = Field(default="", description="Instance size/type (e.g., s-1vcpu-1gb, t3.medium)")
    image: str = Field(default="", description="Snapshot/AMI name or ID")
    tags: list[str] = Field(default_factory=list, description="Instance tags")

    # OS selection
    os: Literal["linux", "windows"] = Field(
        default="linux",
        description="Target OS: linux (SSH) or windows (WinRM)",
    )

    # SSH config (Linux)
    ssh_user: str = Field(default="root", description="SSH username")
    ssh_key: str = Field(default="", description="Path to SSH private key file")
    ssh_password: str = Field(default="", description="SSH password (if key not used)")
    ssh_port: int = Field(default=22, description="SSH port")

    # WinRM config (Windows)
    winrm_user: str = Field(default="Administrator", description="WinRM username")
    winrm_password: str = Field(default="", description="WinRM password")
    winrm_ssl: bool = Field(default=False, description="Use HTTPS for WinRM")
    winrm_port: int | None = Field(default=None, description="WinRM port (auto: 5985/5986)")
    winrm_transport: str = Field(default="ntlm", description="WinRM transport: ntlm, kerberos, credssp")

    # Opsec
    opsec_mode: bool = Field(
        default=False,
        description="Enable opsec mode: command-to-file execution, avoids ps visibility",
    )
    log_commands: bool = Field(
        default=False,
        description="Log all commands and outputs locally for debrief",
    )

    # Lifecycle
    auto_destroy: bool = Field(
        default=True,
        description="Destroy instance after job completes",
    )
    startup_timeout: int = Field(
        default=300,
        description="Seconds to wait for instance to be ready",
    )

    # Static provider fields
    host: str = Field(default="", description="Hostname/IP for static provider")
    hosts: list[CloudHostEntry] = Field(
        default_factory=list,
        description="Multiple hosts for static fleet",
    )

    # AWS-specific
    key_pair_name: str = Field(default="", description="AWS EC2 key pair name")
    security_group: str = Field(default="", description="AWS security group ID")
    subnet_id: str = Field(default="", description="AWS subnet ID")
    iam_instance_profile: str = Field(default="", description="AWS IAM instance profile")

    # DigitalOcean-specific
    vpc_uuid: str = Field(default="", description="DigitalOcean VPC UUID")
    project_id: str = Field(default="", description="DigitalOcean project ID")

    @model_validator(mode="after")
    def set_winrm_port_default(self):
        """Auto-set WinRM port based on SSL setting."""
        if self.winrm_port is None and self.winrm_ssl:
            object.__setattr__(self, "winrm_port", 5986)
        elif self.winrm_port is None and self.os == "windows":
            object.__setattr__(self, "winrm_port", 5985)
        return self


def parse_cloud_field(value: str | dict[str, Any] | CloudConfig | None) -> CloudConfig | None:
    """Parse the cloud field from a job definition.

    Accepts:
    - None → no cloud config
    - str  → profile slug reference
    - dict → inline cloud config (may include 'profile' for base + overrides)
    - CloudConfig → pass through
    """
    if value is None:
        return None
    if isinstance(value, CloudConfig):
        return value
    if isinstance(value, str):
        if not value.strip():
            return None
        return CloudConfig(profile=value)
    if isinstance(value, dict):
        return CloudConfig(**value)
    return None
