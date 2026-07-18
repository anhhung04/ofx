"""Cloud instance and snapshot data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class CloudInstanceInfo:
    """Runtime information about a cloud VPS instance."""

    instance_id: str
    ip: str
    status: str
    provider: str
    region: str = ""
    size: str = ""
    image: str = ""
    name: str = ""
    created_at: datetime | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.status in ("active", "running")

@dataclass
class SnapshotInfo:
    """Information about a cloud snapshot/AMI."""

    snapshot_id: str
    name: str
    provider: str
    region: str = ""
    size_gb: float = 0.0
    status: str = ""
    created_at: datetime | None = None
    metadata: dict = field(default_factory=dict)

@dataclass
class FleetInfo:
    """Information about a fleet of cloud instances."""

    fleet_id: str
    name: str
    provider: str
    instances: list[CloudInstanceInfo] = field(default_factory=list)
    created_at: datetime | None = None

    @property
    def count(self) -> int:
        return len(self.instances)

    @property
    def ips(self) -> list[str]:
        return [i.ip for i in self.instances if i.ip]

    @property
    def all_ready(self) -> bool:
        return all(i.is_ready for i in self.instances)
