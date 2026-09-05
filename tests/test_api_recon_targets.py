"""Tests for ofx.api.recon.targets classification helpers."""

import pytest

from ofx.api.recon.targets import TARGET_TYPES, classify_target, split_targets

class TestClassifyTarget:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("example.com", "domain"),
            ("example.co.uk", "subdomain"),  # ponytail: naive label count
            ("api.example.com", "subdomain"),
            ("deep.api.example.com", "subdomain"),
            ("10.0.0.0/24", "cidr"),
            ("192.168.1.0/30", "cidr"),
            ("2001:db8::/32", "cidr"),
            ("1.2.3.4", "ip"),
            ("2001:db8::1", "ip"),
            ("https://example.com/path", "url"),
            ("http://sub.example.com", "url"),
            (" example.com ", "domain"),
            ("EXAMPLE.COM", "domain"),
        ],
    )
    def test_classify(self, value, expected):
        assert classify_target(value) == expected

    @pytest.mark.parametrize("value", ["", "   ", "not a target", "localhost"])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            classify_target(value)

class TestSplitTargets:
    def test_groups_and_unknown(self):
        groups = split_targets(
            ["example.com", "a.example.com", "10.0.0.0/24", "8.8.8.8",
             "https://x.io", "garbage value", ""]
        )
        assert groups["domain"] == ["example.com"]
        assert groups["subdomain"] == ["a.example.com"]
        assert groups["cidr"] == ["10.0.0.0/24"]
        assert groups["ip"] == ["8.8.8.8"]
        assert groups["url"] == ["https://x.io"]
        assert groups["unknown"] == ["garbage value"]

    def test_all_keys_present(self):
        groups = split_targets([])
        for key in (*TARGET_TYPES, "unknown"):
            assert groups[key] == []
