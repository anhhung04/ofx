"""Cloud provider infrastructure for OFX.

Provides cloud VPS provisioning for running jobs on remote instances.

Usage:
    from ofx.cloud import CloudProviderRegistry, CloudInstanceInfo
    
    provider = CloudProviderRegistry.create("digitalocean", token="...")
    instance = await provider.create_instance(config)
    await provider.wait_until_ready(instance.instance_id)
    # ... run job via SSH/WinRM ...
    await provider.destroy_instance(instance.instance_id)
"""

from ofx.cloud.base import CloudProvider, CloudProviderRegistry
from ofx.cloud.models import CloudInstanceInfo, SnapshotInfo

# Import providers to trigger registration
import ofx.cloud.providers  # noqa: F401

__all__ = [
    "CloudProvider",
    "CloudProviderRegistry",
    "CloudInstanceInfo",
    "SnapshotInfo",
]
