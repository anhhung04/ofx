"""Tests for OFX output types, deduplication, and UserAccount model."""


from ofx.tasks import (
    Port,
    Subdomain,
    Url,
    Vulnerability,
)
from ofx.tasks.output_types import (
    OUTPUT_TYPE_MAP,
    Certificate,
    Confidence,
    Exploit,
    Ip,
    Severity,
)

# ── Output Types ───────────────────────────────────────────────────────────


class TestOutputTypes:
    def test_port_fields(self):
        p = Port(port=80, ip="10.0.0.1", host="web", service_name="http")
        assert p.port == 80
        assert p.host_port == "web:80"
        assert p._type == "port"

    def test_port_host_port_fallback(self):
        p = Port(port=443, ip="10.0.0.1")
        assert p.host_port == "10.0.0.1:443"

    def test_url_fields(self):
        u = Url(url="https://example.com", status_code=200, tech=["nginx"])
        assert u._type == "url"
        assert u.status_code == 200

    def test_vulnerability_severity(self):
        v = Vulnerability(
            name="SQLi", severity=Severity.HIGH, confidence=Confidence.HIGH
        )
        assert v.severity == Severity.HIGH
        assert v._type == "vulnerability"

    def test_subdomain(self):
        s = Subdomain(host="api.example.com", domain="example.com")
        assert s._type == "subdomain"

    def test_to_dict_includes_type_and_uuid(self):
        p = Port(port=22, ip="1.2.3.4")
        d = p.to_dict()
        assert d["_type"] == "port"
        assert "_uuid" in d
        assert len(d["_uuid"]) == 16

    def test_uuid_deterministic(self):
        p1 = Port(port=22, ip="1.2.3.4")
        p2 = Port(port=22, ip="1.2.3.4")
        assert p1._uuid == p2._uuid

    def test_uuid_differs_for_different_data(self):
        p1 = Port(port=22, ip="1.2.3.4")
        p2 = Port(port=80, ip="1.2.3.4")
        assert p1._uuid != p2._uuid

    def test_output_type_map(self):
        assert OUTPUT_TYPE_MAP["port"] is Port
        assert OUTPUT_TYPE_MAP["url"] is Url
        assert OUTPUT_TYPE_MAP["vulnerability"] is Vulnerability
        assert len(OUTPUT_TYPE_MAP) == 11

    def test_all_output_types_have_type_field(self):
        for name, cls in OUTPUT_TYPE_MAP.items():
            # Instantiate with minimal required fields
            if name == "port":
                obj = cls(port=80, ip="1.1.1.1")
            elif name == "url":
                obj = cls(url="http://x")
            elif name == "vulnerability":
                obj = cls(name="test")
            elif name == "tag":
                obj = cls(name="t")
            elif name == "record":
                obj = cls(name="r", type="A")
            elif name == "domain":
                obj = cls(domain="x.com")
            elif name == "certificate":
                obj = cls(host="x")
            elif name == "exploit":
                obj = cls(name="e")
            elif name == "ip":
                obj = cls(ip="1.2.3.4")
            elif name == "subdomain":
                obj = cls(host="a.x.com")
            elif name == "user_account":
                obj = cls(username="admin")
            else:
                continue
            assert obj._type == name

    def test_extra_data(self):
        p = Port(port=80, ip="1.1.1.1", extra_data={"reason": "syn-ack"})
        assert p.extra_data["reason"] == "syn-ack"

    def test_ip_output_type(self):
        i = Ip(ip="192.168.1.1", alive=True)
        assert i._type == "ip"
        assert i.alive is True

    def test_certificate_output_type(self):
        c = Certificate(
            host="example.com", self_signed=False, issuer_cn="Let's Encrypt"
        )
        assert c._type == "certificate"
        assert c.self_signed is False

    def test_exploit_output_type(self):
        e = Exploit(name="EDB-12345", provider="exploitdb", cves=["CVE-2024-1234"])
        assert e._type == "exploit"
        assert "CVE-2024-1234" in e.cves


# ── Deduplication ──────────────────────────────────────────────────────────


class TestDeduplication:
    def test_dedup_removes_duplicates(self):
        from ofx.runner.tasks.runner import TaskRunner

        items = [
            Port(port=80, ip="10.0.0.1"),
            Port(port=80, ip="10.0.0.1"),  # duplicate
            Port(port=443, ip="10.0.0.1"),
        ]
        result = TaskRunner._deduplicate(items)
        assert len(result) == 2
        assert result[0].port == 80
        assert result[1].port == 443

    def test_dedup_preserves_unique(self):
        from ofx.runner.tasks.runner import TaskRunner

        items = [
            Url(url="https://a.com"),
            Url(url="https://b.com"),
            Url(url="https://c.com"),
        ]
        result = TaskRunner._deduplicate(items)
        assert len(result) == 3

    def test_dedup_empty(self):
        from ofx.runner.tasks.runner import TaskRunner
        assert TaskRunner._deduplicate([]) == []


# ── UserAccount Output Type ────────────────────────────────────────────


class TestUserAccount:
    def test_basic_fields(self):
        from ofx.tasks.output_types import UserAccount

        u = UserAccount(
            username="admin",
            password="P@ss",
            domain="CORP",
            host="10.0.0.1",
            account_type="domain",
            privilege_level="admin",
        )
        assert u._type == "user_account"
        assert u.username == "admin"
        assert u.privilege_level == "admin"

    def test_to_dict(self):
        from ofx.tasks.output_types import UserAccount

        u = UserAccount(username="root", host="srv1")
        d = u.to_dict()
        assert d["_type"] == "user_account"
        assert d["username"] == "root"
        assert "_uuid" in d

    def test_uuid_deterministic(self):
        from ofx.tasks.output_types import UserAccount

        u1 = UserAccount(username="admin", domain="CORP")
        u2 = UserAccount(username="admin", domain="CORP")
        assert u1._uuid == u2._uuid

    def test_uuid_different(self):
        from ofx.tasks.output_types import UserAccount

        u1 = UserAccount(username="admin")
        u2 = UserAccount(username="guest")
        assert u1._uuid != u2._uuid

    def test_to_credential(self):
        from ofx.tasks.output_types import UserAccount

        u = UserAccount(
            username="admin",
            password="secret",
            hash="aad3b435b51404ee",
            domain="CORP",
            host="DC01",
            account_type="domain",
            source="secretsdump",
        )
        cred = u.to_credential()
        assert cred.username == "admin"
        assert cred.password == "secret"
        assert cred.hash == "aad3b435b51404ee"
        assert cred.domain == "CORP"
        assert "host=DC01" in cred.comment
        assert "source=secretsdump" in cred.comment

    def test_from_credential(self):
        from dataclasses import dataclass

        from ofx.tasks.output_types import UserAccount

        @dataclass
        class FakeCred:
            username: str = "user1"
            password: str = "pass1"
            hash: str = ""
            domain: str = "LOCAL"
            comment: str = "test"

        cred = FakeCred()
        u = UserAccount.from_credential(cred, host="10.0.0.5", source="mimikatz")
        assert u.username == "user1"
        assert u.password == "pass1"
        assert u.domain == "LOCAL"
        assert u.host == "10.0.0.5"
        assert u.source == "mimikatz"

    def test_in_output_type_map(self):
        from ofx.tasks.output_types import OUTPUT_TYPE_MAP, UserAccount

        assert OUTPUT_TYPE_MAP["user_account"] is UserAccount
