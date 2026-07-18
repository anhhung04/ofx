"""etcd-based registry adapter for distributed coordination"""

import warnings
from typing import Any

from ofx.runner.registry_adapter import SerializedPrefixedRegistryAdapter

try:
    import etcd3

    ETCD_AVAILABLE = True
except Exception:
    ETCD_AVAILABLE = False
    etcd3 = None

class EtcdJobRegistry(SerializedPrefixedRegistryAdapter):
    """etcd-based implementation of registry

    Stores data in etcd for distributed coordination and strong consistency.
    Requires the 'etcd3' package to be installed (optional dependency).

    etcd provides:
    - Strong consistency guarantees
    - Persistent storage
    - Distributed coordination
    - Watch capabilities
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 2379,
        prefix: str = "/ofx/job/",
        timeout: int = 5,
        **kwargs,
    ):
        """Initialize the etcd-based registry

        Args:
            host: etcd server host
            port: etcd server port (default gRPC port)
            prefix: Key prefix for all registry entries
            timeout: Connection timeout in seconds
            **kwargs: Additional etcd3 client arguments
        """
        warnings.warn(
            "EtcdJobRegistry is deprecated and may be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not ETCD_AVAILABLE:
            raise ImportError(
                "etcd support requires the 'etcd3' package. "
                "Install it with: pip install ofx[etcd]"
            )

        self.prefix = prefix
        client_factory = etcd3.client
        self._client = client_factory(
            host=host,
            port=port,
            timeout=timeout,
            **kwargs,
        )
        self._log_backend_initialized(f"at {host}:{port}")

    async def _read_storage_value(self, storage_key: str) -> str | bytes | None:
        client = self._client
        assert client is not None
        value, _ = client.get(storage_key)
        return value

    async def _write_storage_value(self, storage_key: str, json_value: str) -> None:
        client = self._client
        assert client is not None
        client.put(storage_key, json_value)

    async def _storage_key_exists(self, storage_key: str) -> bool:
        client = self._client
        assert client is not None
        value, _ = client.get(storage_key)
        return value is not None

    async def _delete_storage_key(self, storage_key: str) -> None:
        client = self._client
        assert client is not None
        client.delete(storage_key)

    async def _storage_entries(self) -> list[tuple[str, str | bytes | None]]:
        prefix = self._storage_prefix()
        client = self._client
        assert client is not None
        return [
            (self._logical_key(metadata.key.decode()), value)
            for value, metadata in client.get_prefix(prefix)
        ]

    async def _clear_storage(self) -> None:
        prefix = self._storage_prefix()
        client = self._client
        assert client is not None
        client.delete_prefix(prefix)

    async def _close(self) -> None:
        """Close the etcd connection"""
        if self._client:
            self._client.close()
            self._client = None
        self._log_backend_action("Closed")
    _prefix_separator = "/"
