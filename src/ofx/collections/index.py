"""Remote index client — fetch, cache, and search the community collection index."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from ofx.collections.manifest import CollectionIndex, CollectionIndexEntry
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

DEFAULT_INDEX_URL = (
    "https://raw.githubusercontent.com/ofx-workflows/index/main/index.json"
)
INDEX_CACHE_TTL = 3600  # 1 hour


class IndexClient:
    """Fetch and cache the community collection index.

    The index is a JSON file hosted in the ``ofx-workflows/index`` repository::

        {
          "collections": {
            "recon-tools": {
              "name": "recon-tools",
              "description": "Reconnaissance workflows",
              "source": "https://github.com/ofx-workflows/recon-tools",
              "latest": "1.2.0",
              "tags": ["recon", "enumeration"],
              "author": "ofx-community"
            },
            ...
          }
        }
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        index_url: str = DEFAULT_INDEX_URL,
    ):
        from ofx.settings import BASE_DATA_DIR, ensure_dir

        self.cache_dir = ensure_dir(cache_dir or BASE_DATA_DIR / "collections")
        self.index_url = index_url
        self._cache_file = self.cache_dir / "index.json"

    # ------------------------------------------------------------------
    # Fetch / cache
    # ------------------------------------------------------------------

    def fetch(self, force: bool = False) -> CollectionIndex:
        """Return the index, fetching from remote if cache is stale.

        Args:
            force: Bypass cache TTL and always fetch.
        """
        if not force and self._cache_file.exists():
            age = time.time() - self._cache_file.stat().st_mtime
            if age < INDEX_CACHE_TTL:
                return self._load_cache()

        return self._fetch_remote()

    def _load_cache(self) -> CollectionIndex:
        try:
            raw = json.loads(self._cache_file.read_text())
            return CollectionIndex.model_validate(raw)
        except Exception:
            return CollectionIndex()

    def _fetch_remote(self) -> CollectionIndex:
        try:
            logger.debug("Fetching collection index from %s", self.index_url)
            resp = httpx.get(self.index_url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
            self._cache_file.write_text(json.dumps(data, indent=2))
            return CollectionIndex.model_validate(data)
        except httpx.HTTPStatusError as exc:
            logger.warning("Index fetch failed (HTTP %s): %s", exc.response.status_code, exc)
            return self._load_cache()
        except Exception as exc:
            logger.warning("Index fetch failed: %s", exc)
            return self._load_cache()

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------

    def search(self, query: str, force_refresh: bool = False) -> list[CollectionIndexEntry]:
        """Search the community index by name, tag, or description."""
        index = self.fetch(force=force_refresh)
        return index.search(query)

    def get_entry(self, name: str) -> CollectionIndexEntry | None:
        """Lookup a single collection by exact name."""
        index = self.fetch()
        return index.collections.get(name)
