"""Tests for template helper functions: network, ASM, type filters, encoding, and more."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from unittest.mock import patch

from ofx.runner.templates.helpers import (
    _asm_helpers,
    _datetime_helpers,
    _encoding_helpers,
    _file_helpers,
    _hash_helpers,
    _json_helpers,
    _network_helpers,
    _path_helpers,
    _random_helpers,
    _regex_helpers,
    _type_filter_helpers,
    build_all_helpers,
)

# ── File helpers ─────────────────────────────────────────────────────────


class TestFileHelpers:
    def test_read_nonexistent(self):
        h = _file_helpers()
        assert h["file_read"]("/nonexistent/path/xyz") == ""

    def test_read_write_roundtrip(self, tmp_path):
        h = _file_helpers()
        path = str(tmp_path / "test.txt")
        h["file_write"](path, "hello world")
        assert h["file_read"](path) == "hello world"

    def test_append_file(self, tmp_path):
        h = _file_helpers()
        path = str(tmp_path / "append.txt")
        h["file_write"](path, "line1\n")
        h["file_append"](path, "line2\n")
        assert h["file_read"](path) == "line1\nline2\n"

    def test_file_lines(self, tmp_path):
        h = _file_helpers()
        path = str(tmp_path / "lines.txt")
        h["file_write"](path, "a\nb\nc")
        assert h["file_lines"](path) == ["a", "b", "c"]

    def test_file_lines_nonexistent(self):
        h = _file_helpers()
        assert h["file_lines"]("/nonexistent") == []

    def test_file_exists(self, tmp_path):
        h = _file_helpers()
        f = tmp_path / "exists.txt"
        assert not h["file_exists"](str(f))
        f.write_text("x")
        assert h["file_exists"](str(f))

    def test_is_file_and_is_dir(self, tmp_path):
        h = _file_helpers()
        f = tmp_path / "f.txt"
        f.write_text("x")
        assert h["is_file"](str(f))
        assert not h["is_dir"](str(f))
        assert h["is_dir"](str(tmp_path))
        assert not h["is_file"](str(tmp_path))

    def test_write_creates_parent_dirs(self, tmp_path):
        h = _file_helpers()
        path = str(tmp_path / "deep" / "nested" / "file.txt")
        h["file_write"](path, "content")
        assert Path(path).read_text() == "content"


# ── Path helpers ─────────────────────────────────────────────────────────


class TestPathHelpers:
    def test_join_path(self):
        h = _path_helpers()
        result = h["join_path"]("/tmp", "sub", "file.txt")
        assert result == str(Path("/tmp/sub/file.txt"))

    def test_basename(self):
        h = _path_helpers()
        assert h["basename"]("/tmp/dir/file.txt") == "file.txt"

    def test_dirname(self):
        h = _path_helpers()
        assert h["dirname"]("/tmp/dir/file.txt") == "/tmp/dir"

    def test_cwd(self):
        h = _path_helpers()
        assert h["cwd"]() == str(Path.cwd())

    def test_home(self):
        h = _path_helpers()
        assert h["home"]() == str(Path.home())

    def test_glob(self, tmp_path):
        h = _path_helpers()
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        results = h["glob"]("*.txt", str(tmp_path))
        assert len(results) == 2


# ── Encoding helpers ─────────────────────────────────────────────────────


class TestEncodingHelpers:
    def test_b64_roundtrip(self):
        h = _encoding_helpers()
        encoded = h["b64encode"]("hello")
        assert h["b64decode"](encoded) == "hello"

    def test_url_encode_decode(self):
        h = _encoding_helpers()
        encoded = h["url_encode"]("hello world&foo=bar")
        assert "hello" not in encoded or "%" in encoded
        assert h["url_decode"](encoded) == "hello world&foo=bar"

    def test_hex_roundtrip(self):
        h = _encoding_helpers()
        encoded = h["hex_encode"]("test")
        assert h["hex_decode"](encoded) == "test"


# ── Hash helpers ─────────────────────────────────────────────────────────


class TestHashHelpers:
    def test_md5(self):
        h = _hash_helpers()
        expected = hashlib.md5(b"test").hexdigest()
        assert h["md5"]("test") == expected

    def test_sha1(self):
        h = _hash_helpers()
        expected = hashlib.sha1(b"test").hexdigest()
        assert h["sha1"]("test") == expected

    def test_sha256(self):
        h = _hash_helpers()
        expected = hashlib.sha256(b"test").hexdigest()
        assert h["sha256"]("test") == expected


# ── Random helpers ───────────────────────────────────────────────────────


class TestRandomHelpers:
    def test_random_string_default(self):
        h = _random_helpers()
        s = h["random_string"]()
        assert len(s) == 8
        assert s.isalnum()

    def test_random_string_custom_length(self):
        h = _random_helpers()
        assert len(h["random_string"](16)) == 16

    def test_random_string_hex(self):
        h = _random_helpers()
        s = h["random_string"](10, "hex")
        assert all(c in "0123456789abcdef" for c in s)

    def test_random_int(self):
        h = _random_helpers()
        val = h["random_int"](10, 20)
        assert 10 <= val <= 20

    def test_random_port(self):
        h = _random_helpers()
        port = h["random_port"]()
        assert 1024 <= port <= 65535

    def test_uuid_format(self):
        h = _random_helpers()
        u = h["uuid"]()
        assert len(u) == 36
        assert u.count("-") == 4

    def test_token(self):
        h = _random_helpers()
        t = h["token"]()
        assert len(t) > 0


# ── Network helpers ──────────────────────────────────────────────────────


class TestNetworkHelpers:
    def test_is_port_open_closed(self):
        h = _network_helpers()
        assert h["is_port_open"]("192.0.2.1", 99999, timeout=0.1) is False

    def test_is_port_open_exception_path(self):
        h = _network_helpers()
        with patch("socket.socket") as mock_sock:
            mock_sock.side_effect = OSError("fail")
            assert h["is_port_open"]("192.0.2.1", 80) is False

    def test_local_ip_fallback(self):
        h = _network_helpers()
        with patch("socket.socket") as mock_sock:
            mock_sock.side_effect = OSError("no network")
            assert h["local_ip"]() == "127.0.0.1"

    def test_cidr_size_single_ip(self):
        h = _network_helpers()
        assert h["cidr_size"]("192.168.1.1") == 1

    def test_cidr_size_24(self):
        h = _network_helpers()
        assert h["cidr_size"]("192.168.1.0/24") == 254

    def test_cidr_size_16(self):
        h = _network_helpers()
        assert h["cidr_size"]("10.0.0.0/16") == 65534

    def test_cidr_size_8(self):
        h = _network_helpers()
        assert h["cidr_size"]("10.0.0.0/8") == 16777214

    def test_cidr_size_hostname(self):
        h = _network_helpers()
        assert h["cidr_size"]("example.com") == 1

    def test_cidr_size_comma_list(self):
        h = _network_helpers()
        assert h["cidr_size"]("192.168.1.0/24,10.0.0.0/24") == 508


# ── Datetime helpers ─────────────────────────────────────────────────────


class TestDatetimeHelpers:
    def test_now_format(self):
        h = _datetime_helpers()
        result = h["now"]()
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", result)

    def test_now_custom_format(self):
        h = _datetime_helpers()
        result = h["now"]("%Y")
        assert len(result) == 4
        assert result.isdigit()

    def test_timestamp(self):
        h = _datetime_helpers()
        ts = h["timestamp"]()
        assert isinstance(ts, int)
        assert ts > 1_000_000_000


# ── JSON helpers ─────────────────────────────────────────────────────────


class TestJsonHelpers:
    def test_to_json(self):
        h = _json_helpers()
        assert h["to_json"]({"a": 1}) == '{"a": 1}'

    def test_to_json_unencodable(self):
        h = _json_helpers()
        assert h["to_json"](object()) != ""  # uses default=str

    def test_from_json(self):
        h = _json_helpers()
        assert h["from_json"]('{"a": 1}') == {"a": 1}

    def test_from_json_invalid(self):
        h = _json_helpers()
        assert h["from_json"]("not json") is None


# ── Regex helpers ────────────────────────────────────────────────────────


class TestRegexHelpers:
    def test_regex_match(self):
        h = _regex_helpers()
        assert h["regex_match"](r"\d+", "123abc") is True
        assert h["regex_match"](r"\d+", "abc") is False

    def test_regex_search(self):
        h = _regex_helpers()
        assert h["regex_search"](r"\d+", "abc123") is True
        assert h["regex_search"](r"\d+", "abc") is False

    def test_regex_findall(self):
        h = _regex_helpers()
        assert h["regex_findall"](r"\d+", "a1b22c333") == ["1", "22", "333"]

    def test_regex_sub(self):
        h = _regex_helpers()
        assert h["regex_sub"](r"\d", "X", "a1b2") == "aXbX"


# ── Type filter helpers ──────────────────────────────────────────────────


class TestTypeFilterHelpers:
    def test_of_type_filters_correctly(self):
        h = _type_filter_helpers()
        items = [
            {"_type": "port", "port": 80},
            {"_type": "url", "url": "http://example.com"},
            {"_type": "port", "port": 443},
        ]
        result = h["of_type"](items, "port")
        assert len(result) == 2

    def test_of_type_non_list_input(self):
        h = _type_filter_helpers()
        assert h["of_type"]("not a list", "port") == []
        assert h["of_type"](None, "port") == []

    def test_named_filters(self):
        h = _type_filter_helpers()
        items = [
            {"_type": "port", "port": 80},
            {"_type": "url", "url": "http://example.com"},
            {"_type": "vulnerability", "name": "sqli"},
            {"_type": "subdomain", "host": "sub.example.com"},
            {"_type": "ip", "addr": "10.0.0.1"},
            {"_type": "user_account", "username": "admin"},
        ]
        assert len(h["ports"](items)) == 1
        assert len(h["urls"](items)) == 1
        assert len(h["vulns"](items)) == 1
        assert len(h["subdomains"](items)) == 1
        assert len(h["ips"](items)) == 1
        assert len(h["users"](items)) == 1

    def test_empty_list(self):
        h = _type_filter_helpers()
        assert h["ports"]([]) == []

    def test_items_without_type(self):
        h = _type_filter_helpers()
        items = [{"port": 80}, "string_item", 42]
        assert h["ports"](items) == []


# ── ASM helpers (graceful degradation) ───────────────────────────────────


class TestASMHelpers:
    def test_asm_targets_no_module(self):
        """ASM helpers return empty when ofx.asm is not available."""
        h = _asm_helpers()
        with patch.dict("sys.modules", {"ofx.asm.config": None}):
            result = h["asm_targets"]()
            assert result == []

    def test_asm_push_no_module(self):
        h = _asm_helpers()
        with patch.dict("sys.modules", {"ofx.asm.config": None}):
            result = h["asm_push"]([])
            assert result == 0

    def test_asm_scopes_no_module(self):
        h = _asm_helpers()
        with patch.dict("sys.modules", {"ofx.asm.config": None}):
            result = h["asm_scopes"]()
            assert result == []

    def test_asm_scope_assets_no_module(self):
        h = _asm_helpers()
        result = h["asm_scope_assets"]()
        assert result == []

    def test_asm_add_targets_no_module(self):
        h = _asm_helpers()
        result = h["asm_add_targets"](["example.com"])
        assert result == 0


# ── build_all_helpers integration ────────────────────────────────────────


class TestBuildAllHelpers:
    def test_returns_dict(self):
        h = build_all_helpers()
        assert isinstance(h, dict)

    def test_contains_all_categories(self):
        h = build_all_helpers()
        # File helpers
        assert "file_read" in h
        assert "file_write" in h
        # Path helpers
        assert "join_path" in h
        # Encoding
        assert "b64encode" in h
        # Hash
        assert "md5" in h
        assert "sha256" in h
        # Random
        assert "random_string" in h
        assert "uuid" in h
        # Network
        assert "local_ip" in h
        # Datetime
        assert "now" in h
        assert "timestamp" in h
        # JSON
        assert "to_json" in h
        # Regex
        assert "regex_match" in h
        # Type filters
        assert "of_type" in h
        assert "ports" in h
        assert "users" in h
        # ASM
        assert "asm_targets" in h
        # Misc
        assert "is_windows" in h
        assert "platform" in h
