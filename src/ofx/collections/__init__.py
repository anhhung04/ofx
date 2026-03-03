"""OFX Collection Manager — install, update, and discover workflow collections."""

from ofx.collections.manager import CollectionManager, check_version_constraint
from ofx.collections.manifest import CollectionManifest, InstalledCollection

__all__ = [
    "CollectionManager",
    "CollectionManifest",
    "InstalledCollection",
    "check_version_constraint",
]
