"""Cloud provider implementations.

Import all providers here to trigger their registration with CloudProviderRegistry.
"""

# Each provider registers itself via @CloudProviderRegistry.register() on import.
# We use try/except so missing optional dependencies don't break the entire module.

from ofx.cloud.providers.static import StaticProvider  # noqa: F401

try:
    from ofx.cloud.providers.digitalocean import DigitalOceanProvider  # noqa: F401
except ImportError:
    pass

try:
    from ofx.cloud.providers.aws import AWSProvider  # noqa: F401
except ImportError:
    pass
