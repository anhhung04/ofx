"""OFX Collection Manager — install, update, and discover workflow collections."""

from ofx.collections.manager import CollectionManager, check_version_constraint
from ofx.collections.manifest import InstalledCollection

__all__ = [
    "CollectionManager",
    "InstalledCollection",
    "check_version_constraint",
]
