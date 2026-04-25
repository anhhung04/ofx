"""ASM REST API client for OFX integration."""

from __future__ import annotations

import os
from typing import Any

import requests


class ASMClient:
    """Client for the ASM (Attack Surface Management) REST API.

    Connects to the ASM server and provides methods for reading scopes,
    assets, findings, starting scans, and pushing results.

    Parameters
    ----------
    base_url : str
        ASM server URL (e.g., ``https://asm.example.com``).
        Falls back to ``ASM_BASE_URL`` env var.
    token : str | None
        JWT or API token. Falls back to ``ASM_API_TOKEN`` env var.
    timeout : int
        HTTP timeout in seconds (default 30).
    custom_headers : dict[str, str] | None
        Extra HTTP headers applied to every request. Use for Cloudflare
        Access (``CF-Access-Client-Id`` / ``CF-Access-Client-Secret``),
        WAF bypass tokens, or any upstream proxy authentication.
        Falls back to ``ASM_CUSTOM_HEADERS`` env var (comma-separated
        ``Key:Value`` pairs, e.g. ``CF-Access-Client-Id:xxx,CF-Access-Client-Secret:yyy``).
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = 30,
        custom_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("ASM_BASE_URL") or "").rstrip("/")
        self.token = token or os.getenv("ASM_API_TOKEN", "")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        )
        # Apply custom headers (Cloudflare Access, WAF tokens, etc.)
        if custom_headers:
            self._session.headers.update(custom_headers)
        elif env_headers := os.getenv("ASM_CUSTOM_HEADERS", ""):
            for pair in env_headers.split(","):
                pair = pair.strip()
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    self._session.headers[k.strip()] = v.strip()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._session.get(self._url(path), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json: Any = None) -> dict:
        resp = self._session.post(self._url(path), json=json, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ── Scopes ──────────────────────────────────────────

    def list_scopes(self) -> list[dict]:
        """Return all scopes."""
        return self._get("/scopes").get("data", [])

    def get_scope(self, scope_id: str) -> dict:
        """Return scope details."""
        return self._get(f"/scopes/{scope_id}").get("data", {})

    # ── Assets ──────────────────────────────────────────

    def list_assets(
        self,
        scope_id: str,
        asset_type: str | None = None,
        search: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return assets for a scope.

        Returns
        -------
        tuple[list[dict], int]
            (assets, total_count)
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if asset_type:
            params["asset_type"] = asset_type
        if search:
            params["search"] = search
        resp = self._get(f"/scopes/{scope_id}/assets", params=params)
        return resp.get("data", []), resp.get("meta", {}).get("total", 0)

    def list_all_assets(
        self, scope_id: str, asset_type: str | None = None
    ) -> list[dict]:
        """Fetch all assets with automatic pagination."""
        all_assets: list[dict] = []
        offset = 0
        while True:
            batch, total = self.list_assets(
                scope_id, asset_type=asset_type, limit=500, offset=offset
            )
            all_assets.extend(batch)
            if offset + 500 >= total:
                break
            offset += 500
        return all_assets

    def get_subdomains(self, scope_id: str) -> list[str]:
        """Return all subdomain values for a scope."""
        assets = self.list_all_assets(scope_id, asset_type="subdomain")
        return [a["value"] for a in assets if a.get("value")]

    def get_ips(self, scope_id: str) -> list[str]:
        """Return all IP values for a scope."""
        assets = self.list_all_assets(scope_id, asset_type="ip")
        return [a["value"] for a in assets if a.get("value")]

    def get_urls(self, scope_id: str) -> list[str]:
        """Return all URL values for a scope."""
        assets = self.list_all_assets(scope_id, asset_type="url")
        return [a["value"] for a in assets if a.get("value")]

    def get_ports(self, scope_id: str) -> list[str]:
        """Return all port values (host:port) for a scope."""
        assets = self.list_all_assets(scope_id, asset_type="port")
        return [a["value"] for a in assets if a.get("value")]

    # ── Findings ────────────────────────────────────────

    def list_findings(
        self,
        scope_id: str,
        severity: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return findings for a scope."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if severity:
            params["severity"] = severity
        resp = self._get(f"/scopes/{scope_id}/findings", params=params)
        return resp.get("data", []), resp.get("meta", {}).get("total", 0)

    def list_all_findings(
        self, scope_id: str, severity: str | None = None
    ) -> list[dict]:
        """Fetch all findings with automatic pagination."""
        all_findings: list[dict] = []
        offset = 0
        while True:
            batch, total = self.list_findings(
                scope_id, severity=severity, limit=500, offset=offset
            )
            all_findings.extend(batch)
            if offset + 500 >= total:
                break
            offset += 500
        return all_findings

    # ── Targets ─────────────────────────────────────────

    def list_targets(self, scope_id: str) -> list[dict]:
        """Return effective targets for a scope."""
        return self._get(f"/scopes/{scope_id}/targets/effective").get("data", [])

    def add_target(
        self, scope_id: str, value: str, target_type: str = "domain"
    ) -> dict:
        """Add a target to a scope."""
        return self._post(
            f"/scopes/{scope_id}/targets",
            json={"value": value, "target_type": target_type},
        ).get("data", {})

    # ── Scans ───────────────────────────────────────────

    def start_scan(
        self,
        scope_id: str,
        workflow: str,
        profile: str | None = None,
        targets: list[str] | None = None,
    ) -> str:
        """Start an ASM scan. Returns the workflow_run_id."""
        body: dict[str, Any] = {"scope_id": scope_id, "workflow": workflow}
        if profile:
            body["profile"] = profile
        if targets:
            body["targets"] = targets
        resp = self._post("/scans/start", json=body)
        return resp.get("data", {}).get("workflow_run_id", "")

    def get_scan(self, scan_id: str) -> dict:
        """Return scan status and details."""
        return self._get(f"/scans/{scan_id}").get("data", {})

    def cancel_scan(self, scan_id: str) -> None:
        """Cancel a running scan."""
        self._post(f"/scans/{scan_id}/cancel")

    # ── Agents ──────────────────────────────────────────

    def list_agents(self) -> list[dict]:
        """Return all registered agents with health status."""
        return self._get("/agents").get("data", [])

    # ── Workflows ───────────────────────────────────────

    def list_workflows(self) -> list[dict]:
        """Return available workflow definitions."""
        return self._get("/workflows").get("data", [])

    # ── Export helpers ──────────────────────────────────

    def export_scope(self, scope_id: str) -> dict:
        """Export a full scope as a structured dict.

        Returns
        -------
        dict
            Contains ``assets``, ``findings``, ``targets``, and ``statistics``.
        """
        assets = self.list_all_assets(scope_id)
        findings = self.list_all_findings(scope_id)
        targets = self.list_targets(scope_id)

        by_type: dict[str, int] = {}
        for a in assets:
            t = a.get("asset_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        by_sev: dict[str, int] = {}
        for f in findings:
            s = f.get("severity", "info")
            by_sev[s] = by_sev.get(s, 0) + 1

        return {
            "scope_id": scope_id,
            "assets": assets,
            "findings": findings,
            "targets": targets,
            "statistics": {
                "total_assets": len(assets),
                "total_findings": len(findings),
                "by_type": by_type,
                "by_severity": by_sev,
            },
        }

    def assets_as_text(self, scope_id: str, asset_type: str | None = None) -> str:
        """Return assets as newline-separated values for CLI piping."""
        assets = self.list_all_assets(scope_id, asset_type=asset_type)
        return "\n".join(a["value"] for a in assets if a.get("value"))

    # ── Graphs ──────────────────────────────────────────

    def get_attack_paths(self, scope_id: str) -> list[dict]:
        """Return attack path graph data."""
        return self._get("/graph/attack-paths", params={"scope_id": scope_id}).get(
            "data", []
        )

    # ── Dashboard ───────────────────────────────────────

    def get_dashboard(self) -> dict:
        """Return dashboard statistics."""
        return self._get("/dashboard").get("data", {})
