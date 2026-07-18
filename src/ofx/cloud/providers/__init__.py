"""Cloud provider implementations.

Import all providers here to trigger their registration with CloudProviderRegistry.
"""

from contextlib import suppress

from ofx.cloud.providers.static import StaticProvider

with suppress(ImportError):
    from ofx.cloud.providers.digitalocean import DigitalOceanProvider

with suppress(ImportError):
    from ofx.cloud.providers.aws import AWSProvider
