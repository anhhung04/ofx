"""Pydantic models for ASM API responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Scope(BaseModel):
    id: str = ""
    name: str = ""
    scope_type: str = ""
    description: str = ""
    group: str = ""
    engagement_id: str | None = None
    created_at: str = ""
    updated_at: str = ""


class Target(BaseModel):
    id: str = ""
    scope_id: str = ""
    target_type: str = ""  # domain, ip, cidr, url, host
    value: str = ""
    enabled: bool = True
    created_at: str = ""


class Tag(BaseModel):
    id: int = 0
    name: str = ""


class Asset(BaseModel):
    id: str = ""
    scope_id: str = ""
    asset_type: str = ""
    value: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    discovered_at: str = ""
    updated_at: str = ""
    priority: float = 0.0
    is_alive: bool | None = None
    country: str = ""
    region: str = ""
    asn: str = ""
    org: str = ""
    is_cdn: bool | None = None
    is_cloud: bool | None = None
    is_waf: bool | None = None
    title: str = ""
    status_code: int = 0
    tech_stack: str = ""
    fingerprint: str = ""
    tags: list[Tag] = Field(default_factory=list)


class Finding(BaseModel):
    id: str = ""
    asset_id: str = ""
    scope_id: str = ""
    finding_type: str = ""
    severity: str = ""  # critical, high, medium, low, info
    title: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    found_at: str = ""


class ExcludeRule(BaseModel):
    id: str = ""
    scope_id: str | None = None
    rule_type: str = ""  # subnet, ip, domain, port, regex
    value: str = ""
    description: str = ""
    created_at: str = ""


class EffectiveTarget(BaseModel):
    value: str = ""
    target_type: str = ""
    excluded: bool = False
    exclude_by: str | None = None


class BulkImportResult(BaseModel):
    imported: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


class PaginationMeta(BaseModel):
    total: int = 0
    limit: int = 50
    offset: int = 0


class ScanInfo(BaseModel):
    id: str = ""
    workflow_run_id: str = ""
    scope_id: str = ""
    status: str = ""
    workflow: str = ""
    assets_found: int = 0
    findings_found: int = 0
    new_assets: int = 0
    new_findings: int = 0
