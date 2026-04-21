"""Tests for ASM integration module."""

from __future__ import annotations

from ofx.asm.config import ASMConfig
from ofx.asm.export import (
    batch_convert,
    typed_output_to_asm_asset,
    typed_output_to_asm_finding,
)
from ofx.asm.models import (
    Asset,
    BulkImportResult,
    EffectiveTarget,
    ExcludeRule,
    Finding,
    PaginationMeta,
    Scope,
    Target,
)

# ------------------------------------------------------------------
# Model tests
# ------------------------------------------------------------------

class TestModels:
    def test_scope_creation(self):
        s = Scope(id="abc-123", name="test.com", scope_type="domain", group="web")
        assert s.name == "test.com"
        assert s.scope_type == "domain"

    def test_target_creation(self):
        t = Target(id="t1", scope_id="s1", target_type="domain", value="example.com")
        assert t.enabled is True
        assert t.target_type == "domain"

    def test_asset_creation(self):
        a = Asset(
            id="a1",
            scope_id="s1",
            asset_type="subdomain",
            value="sub.example.com",
            source="subfinder",
            is_alive=True,
        )
        assert a.is_alive is True
        assert a.is_cdn is None

    def test_finding_creation(self):
        f = Finding(
            id="f1",
            asset_id="a1",
            scope_id="s1",
            severity="high",
            title="XSS in login",
            source="nuclei",
        )
        assert f.severity == "high"

    def test_exclude_rule(self):
        r = ExcludeRule(rule_type="domain", value="*.internal.com")
        assert r.scope_id is None  # global by default

    def test_bulk_import_result(self):
        r = BulkImportResult(imported=10, skipped=2, errors=["bad line"])
        assert r.imported == 10
        assert len(r.errors) == 1

    def test_effective_target(self):
        t = EffectiveTarget(value="example.com", target_type="domain", excluded=False)
        assert not t.excluded

    def test_pagination_meta_defaults(self):
        m = PaginationMeta()
        assert m.limit == 50
        assert m.offset == 0


# ------------------------------------------------------------------
# Export / conversion tests
# ------------------------------------------------------------------

class TestExport:
    def test_subdomain_to_asset(self):
        item = {"_type": "subdomain", "host": "sub.example.com"}
        result = typed_output_to_asm_asset(item)
        assert result == {"type": "subdomain", "value": "sub.example.com"}

    def test_ip_to_asset(self):
        item = {"_type": "ip", "ip": "1.2.3.4"}
        result = typed_output_to_asm_asset(item)
        assert result == {"type": "ip", "value": "1.2.3.4"}

    def test_url_to_asset(self):
        item = {"_type": "url", "url": "https://example.com/path"}
        result = typed_output_to_asm_asset(item)
        assert result == {"type": "url", "value": "https://example.com/path"}

    def test_port_to_service(self):
        item = {"_type": "port", "ip": "1.2.3.4", "port": 443, "host": "example.com"}
        result = typed_output_to_asm_asset(item)
        assert result == {"type": "service", "value": "1.2.3.4:443"}

    def test_domain_to_asset(self):
        item = {"_type": "domain", "host": "example.com"}
        result = typed_output_to_asm_asset(item)
        assert result == {"type": "domain", "value": "example.com"}

    def test_vulnerability_returns_none_for_asset(self):
        item = {"_type": "vulnerability", "name": "XSS", "severity": "high"}
        assert typed_output_to_asm_asset(item) is None

    def test_vulnerability_to_finding(self):
        item = {
            "_type": "vulnerability",
            "name": "XSS",
            "severity": "high",
            "matched_at": "https://example.com",
        }
        result = typed_output_to_asm_finding(item)
        assert result is not None
        assert result["severity"] == "high"
        assert result["title"] == "XSS"

    def test_unknown_severity_becomes_info(self):
        item = {"_type": "vulnerability", "name": "test", "severity": "unknown"}
        result = typed_output_to_asm_finding(item)
        assert result["severity"] == "info"

    def test_non_vuln_returns_none_for_finding(self):
        item = {"_type": "ip", "ip": "1.2.3.4"}
        assert typed_output_to_asm_finding(item) is None

    def test_unknown_type_returns_none(self):
        item = {"_type": "foobar", "value": "test"}
        assert typed_output_to_asm_asset(item) is None

    def test_batch_convert(self):
        items = [
            {"_type": "subdomain", "host": "a.example.com"},
            {"_type": "subdomain", "host": "b.example.com"},
            {"_type": "ip", "ip": "1.2.3.4"},
            {"_type": "vulnerability", "name": "SQLi", "severity": "critical"},
        ]
        assets, findings = batch_convert(items)
        assert len(assets) == 3
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"

    def test_batch_convert_deduplicates(self):
        items = [
            {"_type": "ip", "ip": "1.2.3.4"},
            {"_type": "ip", "ip": "1.2.3.4"},
            {"_type": "ip", "ip": "5.6.7.8"},
        ]
        assets, _ = batch_convert(items)
        assert len(assets) == 2

    def test_empty_value_skipped(self):
        item = {"_type": "subdomain", "host": ""}
        assert typed_output_to_asm_asset(item) is None


# ------------------------------------------------------------------
# Config tests
# ------------------------------------------------------------------

class TestConfig:
    def test_config_roundtrip(self, tmp_path):
        cfg = ASMConfig(path=tmp_path / "asm.yml")
        assert not cfg.configured

        cfg.url = "http://localhost:8080"
        cfg.token = "asm_test_token123"
        assert cfg.configured
        assert cfg.url == "http://localhost:8080"
        assert cfg.token == "asm_test_token123"

        # Reload from disk
        cfg2 = ASMConfig(path=tmp_path / "asm.yml")
        assert cfg2.url == "http://localhost:8080"
        assert cfg2.token == "asm_test_token123"

    def test_url_strips_trailing_slash(self, tmp_path):
        cfg = ASMConfig(path=tmp_path / "asm.yml")
        cfg.url = "http://localhost:8080/"
        assert cfg.url == "http://localhost:8080"

    def test_default_scope(self, tmp_path):
        cfg = ASMConfig(path=tmp_path / "asm.yml")
        assert cfg.default_scope == ""
        cfg.default_scope = "scope-123"
        assert cfg.default_scope == "scope-123"

    def test_to_dict(self, tmp_path):
        cfg = ASMConfig(path=tmp_path / "asm.yml")
        cfg.url = "http://test:8080"
        cfg.token = "tok"
        d = cfg.to_dict()
        assert d["url"] == "http://test:8080"
        assert d["token"] == "tok"

    def test_nonexistent_file(self, tmp_path):
        cfg = ASMConfig(path=tmp_path / "nonexistent" / "asm.yml")
        assert not cfg.configured
        assert cfg.url == ""
