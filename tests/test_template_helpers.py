"""Tests for template helper functions: network, ASM, type filters, ETL, encoding, and more."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ofx.runner.templates.helpers import (
    _asm_helpers,
    _datetime_helpers,
    _encoding_helpers,
    _etl_helpers,
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

    def test_read_returns_empty_on_read_error(self, tmp_path):
        h = _file_helpers()
        path = tmp_path / "error.txt"
        path.write_text("content")

        with patch.object(Path, "read_text", side_effect=OSError("boom")):
            assert h["file_read"](str(path)) == ""
            assert h["file_lines"](str(path)) == []


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

    def test_asm_targets_uses_default_scope_and_filters_effective(self):
        h = _asm_helpers()
        client = SimpleNamespace(
            find_scope=lambda name: SimpleNamespace(id="scope-id") if name == "demo" else None,
            effective_targets=lambda scope_id: [
                SimpleNamespace(value="a.example", excluded=False, target_type="domain"),
                SimpleNamespace(value="b.example", excluded=True, target_type="domain"),
                SimpleNamespace(value="1.1.1.1", excluded=False, target_type="ip"),
            ],
        )
        with patch("ofx.asm.config.get_asm_client", return_value=client), patch(
            "ofx.asm.config.get_asm_config",
            return_value=SimpleNamespace(default_scope="demo"),
        ):
            result = h["asm_targets"](target_type="domain")
        assert result == ["a.example"]

    def test_asm_scope_assets_returns_dumped_models(self):
        h = _asm_helpers()
        client = SimpleNamespace(
            list_assets=lambda scope_id, limit, asset_type: (
                [
                    SimpleNamespace(model_dump=lambda: {"name": "asset-1"}),
                    SimpleNamespace(model_dump=lambda: {"name": "asset-2"}),
                ],
                None,
            )
        )
        with patch("ofx.asm.config.get_asm_client", return_value=client):
            result = h["asm_scope_assets"](
                scope="12345678-1234-1234-1234-123456789012",
                asset_type="domain",
                limit=2,
            )
        assert result == [{"name": "asset-1"}, {"name": "asset-2"}]


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
        # ETL helpers
        assert "pluck" in h
        assert "to_lines" in h
        assert "sort_by" in h
        assert "unique_by" in h
        assert "where" in h
        assert "group_by" in h
        assert "flatten" in h
        assert "count_by" in h


# ── ETL helpers ──────────────────────────────────────────────────────────

_ETL_ITEMS = [
    {"host": "10.0.0.1", "port": 22, "state": "open", "svc": "ssh"},
    {"host": "10.0.0.1", "port": 80, "state": "open", "svc": "http"},
    {"host": "10.0.0.2", "port": 22, "state": "open", "svc": "ssh"},
    {"host": "10.0.0.2", "port": 443, "state": "open", "svc": "https"},
    {"host": "10.0.0.3", "port": 22, "state": "closed", "svc": "ssh"},
]


class TestETLHelpers:
    def test_pluck(self):
        h = _etl_helpers()
        assert h["pluck"](_ETL_ITEMS, "host") == [
            "10.0.0.1", "10.0.0.1", "10.0.0.2", "10.0.0.2", "10.0.0.3"
        ]

    def test_pluck_non_list(self):
        h = _etl_helpers()
        assert h["pluck"]("not a list", "x") == []

    def test_to_lines(self):
        h = _etl_helpers()
        result = h["to_lines"](_ETL_ITEMS, "host")
        assert result == "10.0.0.1\n10.0.0.1\n10.0.0.2\n10.0.0.2\n10.0.0.3"

    def test_to_lines_custom_sep(self):
        h = _etl_helpers()
        result = h["to_lines"](["a", "b", "c"], sep=",")
        assert result == "a,b,c"

    def test_to_csv(self):
        h = _etl_helpers()
        result = h["to_csv"]([{"a": 1, "b": 2}])
        assert "a" in result and "b" in result
        lines = result.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row

    def test_to_csv_no_headers(self):
        h = _etl_helpers()
        result = h["to_csv"]([{"a": 1}], headers=False)
        assert "a" not in result.split("\n")[0] or result.count("\n") == 0

    def test_to_jsonl(self):
        h = _etl_helpers()
        result = h["to_jsonl"]([{"a": 1}, {"a": 2}])
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_sort_by(self):
        h = _etl_helpers()
        result = h["sort_by"](_ETL_ITEMS, "port")
        ports = [r["port"] for r in result]
        assert ports == sorted(ports)

    def test_sort_by_reverse(self):
        h = _etl_helpers()
        result = h["sort_by"](_ETL_ITEMS, "port", reverse=True)
        ports = [r["port"] for r in result]
        assert ports == sorted(ports, reverse=True)

    def test_sort_by_orders_numbers_before_strings(self):
        h = _etl_helpers()
        items = [
            {"port": "abc"},
            {"port": 80},
            {"port": "22"},
        ]

        result = h["sort_by"](items, "port")

        assert [item["port"] for item in result] == ["22", 80, "abc"]

    def test_unique_by(self):
        h = _etl_helpers()
        result = h["unique_by"](_ETL_ITEMS, "host")
        hosts = [r["host"] for r in result]
        assert len(hosts) == len(set(hosts))

    def test_where(self):
        h = _etl_helpers()
        result = h["where"](_ETL_ITEMS, "state", "open")
        assert len(result) == 4
        assert all(r["state"] == "open" for r in result)

    def test_where_not(self):
        h = _etl_helpers()
        result = h["where_not"](_ETL_ITEMS, "state", "open")
        assert len(result) == 1
        assert result[0]["state"] == "closed"

    def test_first_single(self):
        h = _etl_helpers()
        assert h["first"](_ETL_ITEMS) == _ETL_ITEMS[0]

    def test_first_n(self):
        h = _etl_helpers()
        assert len(h["first"](_ETL_ITEMS, 3)) == 3

    def test_first_empty(self):
        h = _etl_helpers()
        assert h["first"]([]) is None
        assert h["first"]([], 5) == []

    def test_last_single(self):
        h = _etl_helpers()
        assert h["last"](_ETL_ITEMS) == _ETL_ITEMS[-1]

    def test_last_n(self):
        h = _etl_helpers()
        assert len(h["last"](_ETL_ITEMS, 2)) == 2

    def test_group_by(self):
        h = _etl_helpers()
        groups = h["group_by"](_ETL_ITEMS, "state")
        assert "open" in groups
        assert "closed" in groups
        assert len(groups["open"]) == 4
        assert len(groups["closed"]) == 1

    def test_flatten_field(self):
        h = _etl_helpers()
        items = [{"host": "a", "ports": [80, 443]}, {"host": "b", "ports": [22]}]
        result = h["flatten"](items, "ports")
        assert len(result) == 3

    def test_flatten_nested_lists(self):
        h = _etl_helpers()
        assert h["flatten"]([[1, 2], [3], [4, 5]]) == [1, 2, 3, 4, 5]

    def test_count_by(self):
        h = _etl_helpers()
        counts = h["count_by"](_ETL_ITEMS, "state")
        assert counts["open"] == 4
        assert counts["closed"] == 1

    def test_non_list_input_safety(self):
        h = _etl_helpers()
        assert h["sort_by"]("not a list", "x") == []
        assert h["unique_by"](42, "x") == []
        assert h["where"](None, "x", 1) == []
        assert h["group_by"]("bad", "x") == {}
        assert h["flatten"](None) == []
        assert h["count_by"](123, "x") == {}


# ── Jinja2 filter integration ───────────────────────────────────────────


class TestJinjaFilterRegistration:
    """Verify that type filters and ETL helpers work as Jinja2 pipe filters."""

    def test_filters_registered_in_env(self):
        from ofx.runner.templates.resolver import _ensure_filters_registered, _jinja_env

        _ensure_filters_registered(_jinja_env)
        # Type filters
        assert "ports" in _jinja_env.filters
        assert "urls" in _jinja_env.filters
        assert "vulns" in _jinja_env.filters
        assert "of_type" in _jinja_env.filters
        # ETL filters
        assert "pluck" in _jinja_env.filters
        assert "to_lines" in _jinja_env.filters
        assert "sort_by" in _jinja_env.filters
        assert "unique_by" in _jinja_env.filters
        assert "where" in _jinja_env.filters
        assert "flatten" in _jinja_env.filters

    def test_idempotent_registration(self):
        from ofx.runner.templates.resolver import _ensure_filters_registered, _jinja_env

        _ensure_filters_registered(_jinja_env)
        _ensure_filters_registered(_jinja_env)  # must not raise
        assert _jinja_env._ofx_filters_registered is True
