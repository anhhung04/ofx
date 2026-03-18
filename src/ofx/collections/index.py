"""Remote index client — fetch, cache, and search the community collection index."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ofx.collections.manifest import CollectionIndex, CollectionIndexEntry
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

DEFAULT_INDEX_URL = (
    "https://raw.githubusercontent.com/ofx-workflows/index/refs/heads/master/index.json"
)
INDEX_CACHE_TTL = 3600  # 1 hour


def _resolve_index_url(url: str) -> str:
    """If *url* looks like a GitHub repo URL, convert to an API-compatible URL.

    For raw.githubusercontent.com the URL can be used directly (with token in header).
    For ``https://github.com/<owner>/<repo>`` convert to the contents API endpoint
    so that private repos work too.
    """
    parsed = urlparse(url)
    # Already a raw URL — fine as-is
    if parsed.hostname == "raw.githubusercontent.com":
        return url
    # api.github.com — fine as-is
    if parsed.hostname == "api.github.com":
        return url
    # Convert https://github.com/<owner>/<repo>/... shorthand
    if parsed.hostname in ("github.com", "www.github.com"):
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1].removesuffix(".git")
            # Assume the file is index.json on the default branch
            return (
                f"https://api.github.com/repos/{owner}/{repo}"
                f"/contents/index.json?ref=master"
            )
    return url


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

    For private index repos, set ``OFX_GITHUB_TOKEN`` (or pass *github_token*)
    and optionally ``OFX_COLLECTION_INDEX_URL`` to point to your private repo.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        index_url: str = "",
        github_token: str = "",
    ):
        from ofx.settings import BASE_DATA_DIR, ensure_dir

        self.cache_dir = ensure_dir(cache_dir or BASE_DATA_DIR / "collections")

        # Resolve URL: explicit arg → settings override → default
        self.index_url = index_url or settings.collection_index_url or DEFAULT_INDEX_URL

        # Resolve token: explicit arg → settings → gh CLI
        from ofx.settings import get_github_token

        self.github_token = github_token or get_github_token()
        self._cache_file = self.cache_dir / "index.json"

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        """Return HTTP headers, including auth when a token is configured."""
        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

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
        headers = self._build_headers()
        url = self.index_url

        # If a token is set and the URL is the default raw.githubusercontent
        # URL, switch to the API endpoint so private repos are accessible.
        if self.github_token and url == DEFAULT_INDEX_URL:
            url = _resolve_index_url(url)

        try:
            logger.debug("Fetching collection index from %s", url)
            resp = httpx.get(url, timeout=15, follow_redirects=True, headers=headers)
            resp.raise_for_status()

            data = resp.json()

            # GitHub API returns a wrapper with "content" (base64) for the
            # contents endpoint.  Unwrap if present.
            if "content" in data and "encoding" in data:
                import base64

                raw_bytes = base64.b64decode(data["content"])
                data = json.loads(raw_bytes)

            self._cache_file.write_text(json.dumps(data, indent=2))
            return CollectionIndex.model_validate(data)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Index fetch failed (HTTP %s): %s", exc.response.status_code, exc
            )
            return self._load_cache()
        except Exception as exc:
            logger.warning("Index fetch failed: %s", exc)
            return self._load_cache()

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------

    def search(
        self, query: str, force_refresh: bool = False
    ) -> list[CollectionIndexEntry]:
        """Search the community index by name, tag, or description."""
        index = self.fetch(force=force_refresh)
        return index.search(query)

    def get_entry(self, name: str) -> CollectionIndexEntry | None:
        """Lookup a single collection by exact name."""
        index = self.fetch()
        return index.collections.get(name)
