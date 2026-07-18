"""Cloud provider infrastructure for OFX.

Provides cloud VPS provisioning for running jobs on remote instances.

Usage:
    from ofx.cloud import CloudProviderRegistry, CloudInstanceInfo

    provider = CloudProviderRegistry.create("digitalocean", token="...")
    instance = await provider.create_instance(config)
    await provider.wait_until_ready(instance.instance_id)
    await provider.destroy_instance(instance.instance_id)
"""

import ofx.cloud.providers
from ofx.cloud.base import CloudProvider, CloudProviderRegistry
from ofx.cloud.models import CloudInstanceInfo, SnapshotInfo

__all__ = [
    "CloudProvider",
    "CloudProviderRegistry",
    "CloudInstanceInfo",
    "SnapshotInfo",
]
