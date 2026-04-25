"""Async HTTP client for the ASM REST API.

All methods are synchronous wrappers around ``httpx`` so they can be
called from both sync CLI commands and async runner code.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ofx.asm.models import (
    Asset,
    BulkImportResult,
    EffectiveTarget,
    ExcludeRule,
    Finding,
    PaginationMeta,
    ScanInfo,
    Scope,
    Target,
)
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class ASMError(Exception):
    """Raised when the ASM API returns an error."""

    def __init__(self, message: str, status_code: int = 0):
        self.status_code = status_code
        super().__init__(message)


class ASMClient:
    """Synchronous client for the ASM REST API (``/api/v1``)."""

    API_PREFIX = "/api/v1"

    def __init__(
        self,
        base_url: str,
        api_token: str = "",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self.base_url}{self.API_PREFIX}",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # Low-level request helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | list | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = self._client.request(method, path, json=json_body, params=params)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("error", resp.text)
            except Exception:
                logger.debug(
                    "Failed to parse ASM error response as JSON", exc_info=True
                )
                msg = resp.text
            raise ASMError(msg, status_code=resp.status_code)
        return resp.json()

    def _get(self, path: str, **params) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self._request("GET", path, params=clean)

    def _post(
        self, path: str, body: dict | list | None = None, **params
    ) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self._request("POST", path, json_body=body, params=clean)

    def _put(self, path: str, body: dict | None = None) -> dict[str, Any]:
        return self._request("PUT", path, json_body=body)

    def _delete(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", path)

    def _patch(self, path: str, body: dict | None = None) -> dict[str, Any]:
        return self._request("PATCH", path, json_body=body)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> bool:
        """Check server health. Returns True if healthy."""
        try:
            self._get("/health")
            return True
        except Exception:
            logger.debug("ASM health check failed", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Scopes
    # ------------------------------------------------------------------

    def list_scopes(self, group: str = "") -> list[Scope]:
        data = self._get("/scopes", group=group)
        return [Scope.model_validate(s) for s in (data.get("data") or [])]

    def get_scope(self, scope_id: str) -> Scope:
        data = self._get(f"/scopes/{scope_id}")
        return Scope.model_validate(data.get("data", {}))

    def create_scope(
        self,
        name: str,
        scope_type: str = "domain",
        description: str = "",
        group: str = "",
    ) -> Scope:
        body = {"name": name, "scope_type": scope_type}
        if description:
            body["description"] = description
        if group:
            body["group"] = group
        data = self._post("/scopes", body)
        return Scope.model_validate(data.get("data", {}))

    def update_scope(self, scope_id: str, **fields) -> Scope:
        data = self._put(f"/scopes/{scope_id}", fields)
        return Scope.model_validate(data.get("data", {}))

    def delete_scope(self, scope_id: str) -> None:
        self._delete(f"/scopes/{scope_id}")

    def find_scope(self, name: str) -> Scope | None:
        """Find a scope by name (case-insensitive). Returns None if not found."""
        for scope in self.list_scopes():
            if scope.name.lower() == name.lower():
                return scope
        return None

    # ------------------------------------------------------------------
    # Targets
    # ------------------------------------------------------------------

    def list_targets(self, scope_id: str) -> list[Target]:
        data = self._get(f"/scopes/{scope_id}/targets")
        return [Target.model_validate(t) for t in (data.get("data") or [])]

    def effective_targets(self, scope_id: str) -> list[EffectiveTarget]:
        data = self._get(f"/scopes/{scope_id}/targets/effective")
        return [EffectiveTarget.model_validate(t) for t in (data.get("data") or [])]

    def add_target(
        self, scope_id: str, value: str, target_type: str = "domain"
    ) -> Target:
        body = {"target_type": target_type, "value": value}
        data = self._post(f"/scopes/{scope_id}/targets", body)
        return Target.model_validate(data.get("data", {}))

    def bulk_import_targets(
        self,
        scope_id: str,
        targets: list[str],
        auto_detect: bool = True,
    ) -> BulkImportResult:
        body: dict[str, Any] = {
            "format": "text",
            "targets": targets,
            "auto_detect": auto_detect,
        }
        data = self._post(f"/scopes/{scope_id}/targets/bulk", body)
        return BulkImportResult.model_validate(data.get("data", {}))

    def delete_target(self, target_id: str) -> None:
        self._delete(f"/targets/{target_id}")

    def toggle_target(self, target_id: str) -> None:
        self._patch(f"/targets/{target_id}/toggle")

    # ------------------------------------------------------------------
    # Exclude rules
    # ------------------------------------------------------------------

    def list_exclude_rules(self, scope_id: str) -> list[ExcludeRule]:
        data = self._get(f"/scopes/{scope_id}/exclude-rules")
        return [ExcludeRule.model_validate(r) for r in (data.get("data") or [])]

    def add_exclude_rule(
        self,
        scope_id: str,
        rule_type: str,
        value: str,
        description: str = "",
    ) -> ExcludeRule:
        body: dict[str, str] = {"rule_type": rule_type, "value": value}
        if description:
            body["description"] = description
        data = self._post(f"/scopes/{scope_id}/exclude-rules", body)
        return ExcludeRule.model_validate(data.get("data", {}))

    def delete_exclude_rule(self, rule_id: str) -> None:
        self._delete(f"/exclude-rules/{rule_id}")

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------

    def list_assets(
        self,
        scope_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        asset_type: str = "",
        source: str = "",
        search: str = "",
    ) -> tuple[list[Asset], PaginationMeta]:
        data = self._get(
            f"/scopes/{scope_id}/assets",
            limit=limit,
            offset=offset,
            asset_type=asset_type,
            source=source,
            search=search,
        )
        assets = [Asset.model_validate(a) for a in (data.get("data") or [])]
        meta = PaginationMeta.model_validate(data.get("meta", {}))
        return assets, meta

    def get_asset(self, asset_id: str) -> Asset:
        data = self._get(f"/assets/{asset_id}")
        return Asset.model_validate(data.get("data", {}))

    def delete_asset(self, asset_id: str) -> None:
        self._delete(f"/assets/{asset_id}")

    # ------------------------------------------------------------------
    # Findings
    # ------------------------------------------------------------------

    def list_findings(
        self,
        scope_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        severity: str = "",
        source: str = "",
    ) -> tuple[list[Finding], PaginationMeta]:
        data = self._get(
            f"/scopes/{scope_id}/findings",
            limit=limit,
            offset=offset,
            severity=severity,
            source=source,
        )
        findings = [Finding.model_validate(f) for f in (data.get("data") or [])]
        meta = PaginationMeta.model_validate(data.get("meta", {}))
        return findings, meta

    # ------------------------------------------------------------------
    # Import (push OFX results as assets)
    # ------------------------------------------------------------------

    def import_generic(
        self,
        scope_id: str,
        items: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Import assets via the generic JSON format.

        Each item should have ``type`` and ``value`` keys.
        """
        data = self._post("/import", items, scope_id=scope_id, format="generic")
        return data.get("data", {})

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_assets(self, scope_id: str, fmt: str = "json") -> list[dict[str, Any]]:
        data = self._get(f"/scopes/{scope_id}/export/assets", format=fmt)
        return data.get("data") or []

    def export_findings(self, scope_id: str, fmt: str = "json") -> list[dict[str, Any]]:
        data = self._get(f"/scopes/{scope_id}/export/findings", format=fmt)
        return data.get("data") or []

    # ------------------------------------------------------------------
    # Scans
    # ------------------------------------------------------------------

    def start_scan(
        self,
        scope_id: str,
        workflow_name: str = "",
        profile_name: str = "",
        scan_name: str = "",
    ) -> ScanInfo:
        body: dict[str, Any] = {"scope_id": scope_id}
        if workflow_name:
            body["workflow_name"] = workflow_name
        if profile_name:
            body["profile_name"] = profile_name
        if scan_name:
            body["scan_name"] = scan_name
        data = self._post("/scans/start", body)
        return ScanInfo.model_validate(data.get("data", {}))

    def get_scan(self, scan_id: str) -> ScanInfo:
        data = self._get(f"/scans/{scan_id}")
        return ScanInfo.model_validate(data.get("data", {}))
