"""Session data models for detached job execution."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field

from ofx.models.base import OFXBaseModel


class SessionStatus(str, Enum):
    """Lifecycle states for a detached session."""

    PROVISIONING = "provisioning"
    UPLOADING = "uploading"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    FETCHED = "fetched"
    ENCRYPTED = "encrypted"
    DESTROYED = "destroyed"


class SessionTarget(str, Enum):
    """Where the session executes."""

    LOCAL = "local"
    CLOUD = "cloud"


class Session(OFXBaseModel):
    """Persistent session metadata for a detached job run."""

    model_config = {**OFXBaseModel.model_config, "extra": "allow"}

    # Identity
    id: str = Field(..., description="Short session identifier (8-char hex)")
    name: str = Field(default="", description="User-provided session name or tag")

    # What to run
    workflow_file: str = Field(..., description="Workflow path or name")
    job_id: str = Field(default="", description="Specific job ID (empty = all jobs)")

    # Execution target
    target: SessionTarget = Field(
        default=SessionTarget.LOCAL,
        description="Where to run: local or cloud",
    )
    status: SessionStatus = Field(
        default=SessionStatus.PROVISIONING,
        description="Current session lifecycle state",
    )

    # Cloud fields (empty for local)
    cloud_profile: str = Field(default="", description="Cloud profile name")
    cloud_provider: str = Field(default="", description="Provider name")
    instance_id: str = Field(default="", description="Cloud instance ID")
    instance_ip: str = Field(default="", description="VPS IP address")

    # Process tracking
    remote_pid: int | None = Field(
        default=None, description="PID of the detached process"
    )
    remote_work_dir: str = Field(
        default="", description="Working directory on remote/local target"
    )
    remote_log_file: str = Field(
        default="", description="Path to the output log on remote/local target"
    )

    # Timestamps
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the session was submitted",
    )
    finished_at: datetime | None = Field(
        default=None, description="When the session completed/failed"
    )

    # Local paths
    output_path: str = Field(
        default="", description="Local directory for session data"
    )
    results_path: str = Field(
        default="", description="Local directory where fetched results live"
    )

    # At-rest encryption (transparent — key stored locally in session metadata)
    at_rest_key: str = Field(
        default="",
        description="Random AES key for at-rest encryption on VPS/local (hex-encoded)",
    )
    at_rest_encrypted: bool = Field(
        default=False,
        description="Whether output on the remote/local target is encrypted at rest",
    )

    # User-requested encryption (passphrase-based, applied at fetch time)
    encrypted: bool = Field(default=False, description="Whether results are encrypted")
    encrypted_file: str = Field(
        default="", description="Path to encrypted results archive"
    )

    # Inputs & metadata
    inputs: dict[str, Any] = Field(
        default_factory=dict, description="Workflow inputs passed at submit time"
    )
    error: str = Field(default="", description="Error message if failed")
    tags: dict[str, str] = Field(
        default_factory=dict, description="Arbitrary key-value tags"
    )

    # Connection details (for cloud reconnection)
    ssh_user: str = Field(default="root", description="SSH user for reconnection")
    ssh_port: int = Field(default=22, description="SSH port")
    ssh_key: str = Field(default="", description="SSH key path")
    ssh_password: str = Field(default="", description="SSH password")
    os_type: str = Field(default="linux", description="linux or windows")

    def is_running(self) -> bool:
        """Whether the session is still actively executing."""
        return self.status in (
            SessionStatus.PROVISIONING,
            SessionStatus.UPLOADING,
            SessionStatus.RUNNING,
        )

    def is_done(self) -> bool:
        """Whether the session has reached a terminal state."""
        return self.status in (
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELED,
            SessionStatus.FETCHED,
            SessionStatus.ENCRYPTED,
            SessionStatus.DESTROYED,
        )

    def age_display(self) -> str:
        """Human-readable age string."""
        delta = datetime.now(timezone.utc) - self.started_at
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h {(secs % 3600) // 60}m"
        return f"{secs // 86400}d {(secs % 86400) // 3600}h"
