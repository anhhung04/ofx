"""Tests for fleet input parsing, distribution, and matrix expansion."""

from __future__ import annotations

from pathlib import Path

import pytest

from ofx.cloud.fleet_distributor import FleetDistributor, expand_fleet_to_matrix
from ofx.cloud.fleet_input import FleetInputParser, split_subnet

# ── FleetInputParser: basic parsing ──────────────────────────────────────


class TestFleetInputParserBasic:
    """Core parsing of IPs, CIDRs, ranges, hostnames."""

    def test_single_ip(self):
        targets = FleetInputParser().parse("10.0.0.1")
        assert targets == ["10.0.0.1"]

    def test_multiple_ips_comma_separated(self):
        targets = FleetInputParser().parse("10.0.0.1,10.0.0.2,10.0.0.3")
        assert targets == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_hostname(self):
        targets = FleetInputParser().parse("target.example.com")
        assert targets == ["target.example.com"]

    def test_list_input(self):
        targets = FleetInputParser().parse(["10.0.0.1", "10.0.0.2"])
        assert targets == ["10.0.0.1", "10.0.0.2"]

    def test_deduplication(self):
        targets = FleetInputParser().parse(["10.0.0.1", "10.0.0.1", "10.0.0.2"])
        assert targets == ["10.0.0.1", "10.0.0.2"]

    def test_blank_lines_skipped(self):
        targets = FleetInputParser().parse("10.0.0.1\n\n10.0.0.2\n\n")
        assert targets == ["10.0.0.1", "10.0.0.2"]

    def test_comments_skipped(self):
        targets = FleetInputParser().parse("10.0.0.1\n# comment\n10.0.0.2")
        assert targets == ["10.0.0.1", "10.0.0.2"]

    def test_inline_comment_stripped(self):
        targets = FleetInputParser().parse("10.0.0.1 # web server")
        assert targets == ["10.0.0.1"]

    def test_mixed_types(self):
        data = ["10.0.0.1", "target.example.com", "192.168.1.0/30"]
        targets = FleetInputParser().parse(data)
        assert "10.0.0.1" in targets
        assert "target.example.com" in targets
        # /30 expands to 2 hosts
        assert "192.168.1.1" in targets
        assert "192.168.1.2" in targets


# ── FleetInputParser: CIDR expansion ────────────────────────────────────


class TestFleetInputParserCIDR:
    """CIDR expansion and preserve-CIDR mode."""

    def test_expand_cidr_slash_30(self):
        targets = FleetInputParser(expand_cidrs=True).parse("192.168.1.0/30")
        # /30 has 2 usable hosts
        assert targets == ["192.168.1.1", "192.168.1.2"]

    def test_expand_cidr_slash_32(self):
        targets = FleetInputParser(expand_cidrs=True).parse("10.0.0.5/32")
        assert targets == ["10.0.0.5"]

    def test_no_expand_cidrs(self):
        targets = FleetInputParser(expand_cidrs=False).parse("192.168.1.0/24")
        assert targets == ["192.168.1.0/24"]

    def test_expand_cidr_slash_29(self):
        targets = FleetInputParser(expand_cidrs=True).parse("10.0.0.0/29")
        # /29 = 8 addresses, 6 usable hosts
        assert len(targets) == 6
        assert "10.0.0.1" in targets
        assert "10.0.0.6" in targets
        # Network and broadcast excluded by .hosts()
        assert "10.0.0.0" not in targets
        assert "10.0.0.7" not in targets

    def test_preserve_cidrs_mode(self):
        data = ["10.0.0.1", "192.168.1.0/24", "host.example.com"]
        targets = FleetInputParser().parse_preserving_cidrs(data)
        assert "192.168.1.0/24" in targets
        assert "10.0.0.1" in targets

    def test_invalid_cidr_treated_as_hostname(self):
        targets = FleetInputParser().parse("not-a-cidr/foo")
        assert targets == ["not-a-cidr/foo"]


# ── FleetInputParser: IP range expansion ────────────────────────────────


class TestFleetInputParserRanges:
    """Full and short IP range expansion."""

    def test_full_range(self):
        targets = FleetInputParser().parse("10.0.0.1-10.0.0.5")
        assert targets == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"]

    def test_short_range(self):
        targets = FleetInputParser().parse("10.0.0.1-5")
        assert targets == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"]

    def test_reversed_full_range_swaps(self):
        targets = FleetInputParser().parse("10.0.0.5-10.0.0.1")
        assert targets == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"]

    def test_reversed_short_range_swaps(self):
        targets = FleetInputParser().parse("10.0.0.5-1")
        assert targets == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"]

    def test_single_ip_range(self):
        targets = FleetInputParser().parse("10.0.0.3-3")
        assert targets == ["10.0.0.3"]

    def test_short_range_invalid_octet_skipped(self):
        """Short range with octets >255 should produce no results."""
        targets = FleetInputParser().parse("10.0.0.250-300")
        assert targets == []


# ── FleetInputParser: file reading ──────────────────────────────────────


class TestFleetInputParserFiles:
    """File-based input reading."""

    def test_read_from_file(self, tmp_path: Path):
        target_file = tmp_path / "targets.txt"
        target_file.write_text("10.0.0.1\n10.0.0.2\n# comment\n10.0.0.3\n")
        targets = FleetInputParser().parse(str(target_file))
        assert targets == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_recursive_file_inclusion(self, tmp_path: Path):
        inner = tmp_path / "inner.txt"
        inner.write_text("10.0.0.10\n10.0.0.11\n")
        outer = tmp_path / "outer.txt"
        outer.write_text(f"10.0.0.1\n{inner}\n10.0.0.2\n")
        targets = FleetInputParser().parse(str(outer))
        assert "10.0.0.1" in targets
        assert "10.0.0.10" in targets
        assert "10.0.0.11" in targets
        assert "10.0.0.2" in targets

    def test_recursive_loop_protection(self, tmp_path: Path):
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text(f"10.0.0.1\n{file_b}\n")
        file_b.write_text(f"10.0.0.2\n{file_a}\n")
        # Should not infinite loop — cycle detection stops it
        targets = FleetInputParser().parse(str(file_a))
        assert "10.0.0.1" in targets
        assert "10.0.0.2" in targets


# ── FleetInputParser: exclusion ──────────────────────────────────────────


class TestFleetInputParserExclusion:
    """Exclusion of IPs and networks."""

    def test_exclude_single_ip(self):
        parser = FleetInputParser(exclude=["10.0.0.2"])
        targets = parser.parse(["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        assert targets == ["10.0.0.1", "10.0.0.3"]

    def test_exclude_cidr(self):
        parser = FleetInputParser(exclude=["10.0.0.0/30"])
        targets = parser.parse(["10.0.0.1", "10.0.0.2", "10.0.0.5"])
        # 10.0.0.1 and 10.0.0.2 are in /30 (0-3)
        assert targets == ["10.0.0.5"]

    def test_exclude_hostname(self):
        parser = FleetInputParser(exclude=["bad.example.com"])
        targets = parser.parse(["good.example.com", "bad.example.com"])
        assert targets == ["good.example.com"]

    def test_exclude_does_not_affect_unrelated(self):
        parser = FleetInputParser(exclude=["10.0.0.99"])
        targets = parser.parse(["10.0.0.1", "10.0.0.2"])
        assert targets == ["10.0.0.1", "10.0.0.2"]


# ── FleetInputParser: edge cases ─────────────────────────────────────────


class TestFleetInputParserEdgeCases:
    """Edge cases and empty inputs."""

    def test_empty_string(self):
        targets = FleetInputParser().parse("")
        assert targets == []

    def test_empty_list(self):
        targets = FleetInputParser().parse([])
        assert targets == []

    def test_whitespace_only(self):
        targets = FleetInputParser().parse("   \n   \n   ")
        assert targets == []

    def test_comments_only(self):
        targets = FleetInputParser().parse("# just a comment\n# another")
        assert targets == []


# ── FleetDistributor ─────────────────────────────────────────────────────


class TestFleetDistributorChunk:
    """Chunk distribution mode."""

    def test_even_split(self):
        targets = [f"10.0.0.{i}" for i in range(1, 11)]
        chunks = FleetDistributor().distribute(targets, count=2, mode="chunk")
        assert len(chunks) == 2
        assert len(chunks[0]) == 5
        assert len(chunks[1]) == 5

    def test_uneven_split(self):
        targets = [f"10.0.0.{i}" for i in range(1, 8)]  # 7 targets
        chunks = FleetDistributor().distribute(targets, count=3, mode="chunk")
        assert len(chunks) == 3
        total = sum(len(c) for c in chunks)
        assert total == 7
        # First chunks get extra
        assert len(chunks[0]) >= len(chunks[2])

    def test_more_instances_than_targets(self):
        targets = ["10.0.0.1", "10.0.0.2"]
        chunks = FleetDistributor().distribute(targets, count=5, mode="chunk")
        # Should reduce to 2 instances
        assert len(chunks) == 2
        assert all(len(c) == 1 for c in chunks)

    def test_single_instance(self):
        targets = [f"10.0.0.{i}" for i in range(1, 6)]
        chunks = FleetDistributor().distribute(targets, count=1, mode="chunk")
        assert len(chunks) == 1
        assert len(chunks[0]) == 5


class TestFleetDistributorRoundRobin:
    """Round-robin distribution mode."""

    def test_round_robin_even(self):
        targets = [f"10.0.0.{i}" for i in range(1, 7)]  # 6 targets
        chunks = FleetDistributor().distribute(targets, count=3, mode="round-robin")
        assert len(chunks) == 3
        assert all(len(c) == 2 for c in chunks)

    def test_round_robin_interleaves(self):
        targets = ["a", "b", "c", "d", "e", "f"]
        chunks = FleetDistributor().distribute(targets, count=3, mode="round-robin")
        assert chunks[0] == ["a", "d"]
        assert chunks[1] == ["b", "e"]
        assert chunks[2] == ["c", "f"]

    def test_round_robin_uneven(self):
        targets = [f"10.0.0.{i}" for i in range(1, 6)]  # 5 targets
        chunks = FleetDistributor().distribute(targets, count=3, mode="round-robin")
        total = sum(len(c) for c in chunks)
        assert total == 5


class TestFleetDistributorSubnet:
    """Subnet-aware distribution mode."""

    def test_same_subnet_grouped(self):
        targets = [
            "10.0.0.1",
            "10.0.0.2",
            "10.0.0.3",  # /24 group 1
            "10.0.1.1",
            "10.0.1.2",
            "10.0.1.3",  # /24 group 2
        ]
        chunks = FleetDistributor().distribute(targets, count=2, mode="subnet")
        assert len(chunks) == 2
        # Each chunk should contain IPs from the same subnet
        for chunk in chunks:
            subnets = set()
            for ip in chunk:
                parts = ip.rsplit(".", 1)
                subnets.add(parts[0])
            # All IPs should be from the same /24
            assert len(subnets) == 1

    def test_hostnames_grouped_separately(self):
        targets = ["10.0.0.1", "10.0.0.2", "host.example.com"]
        chunks = FleetDistributor().distribute(targets, count=2, mode="subnet")
        all_targets = [t for c in chunks for t in c]
        assert sorted(all_targets) == sorted(targets)


class TestFleetDistributorLine:
    """Line distribution mode (one target per instance)."""

    def test_line_mode(self):
        targets = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
        chunks = FleetDistributor().distribute(targets, count=3, mode="line")
        assert len(chunks) == 3
        assert all(len(c) == 1 for c in chunks)

    def test_line_mode_ignores_count(self):
        targets = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
        # Count doesn't matter in line mode — one per target
        chunks = FleetDistributor().distribute(targets, count=10, mode="line")
        assert len(chunks) == 3


class TestFleetDistributorEdgeCases:
    """Edge cases for FleetDistributor."""

    def test_empty_targets(self):
        chunks = FleetDistributor().distribute([], count=3, mode="chunk")
        assert chunks == []

    def test_zero_count(self):
        chunks = FleetDistributor().distribute(["10.0.0.1"], count=0, mode="chunk")
        assert chunks == []

    def test_unknown_mode_falls_back(self):
        targets = ["10.0.0.1", "10.0.0.2"]
        chunks = FleetDistributor().distribute(targets, count=2, mode="bad_mode")
        assert len(chunks) == 2


# ── split_subnet ─────────────────────────────────────────────────────────


class TestSplitSubnet:
    """Tests for the split_subnet utility."""

    def test_split_slash_24_into_4(self):
        result = split_subnet("10.0.0.0/24", 4)
        assert len(result) == 4
        assert "10.0.0.0/26" in result

    def test_split_single(self):
        result = split_subnet("10.0.0.0/24", 1)
        assert result == ["10.0.0.0/24"]

    def test_split_slash_16_into_4(self):
        result = split_subnet("10.0.0.0/16", 4)
        assert len(result) == 4
        assert all("/18" in s for s in result)

    def test_min_prefix_limits_split(self):
        result = split_subnet("10.0.0.0/30", 8, min_prefix=32)
        # /30 can split into at most /32s (4 addresses)
        assert len(result) <= 8


# ── expand_fleet_to_matrix ───────────────────────────────────────────────


class TestExpandFleetToMatrix:
    """Integration tests for expand_fleet_to_matrix."""

    def test_basic_expansion(self, tmp_path: Path):
        target_file = tmp_path / "targets.txt"
        target_file.write_text("10.0.0.1\n10.0.0.2\n10.0.0.3\n10.0.0.4\n")

        config = {
            "count": 2,
            "input": str(target_file),
            "distribution": "chunk",
        }
        combos, chunk_files = expand_fleet_to_matrix(config)
        try:
            assert len(combos) == 2
            assert len(chunk_files) == 2
            # Each combo has fleet context
            for combo in combos:
                assert "fleet_index" in combo
                assert "fleet_total" in combo
                assert "fleet_input_file" in combo
                assert "fleet_target_count" in combo
                assert "fleet_input" in combo
            # Total targets distributed
            total = sum(c["fleet_target_count"] for c in combos)
            assert total == 4
        finally:
            for f in chunk_files:
                f.unlink(missing_ok=True)
            if chunk_files:
                chunk_files[0].parent.rmdir()

    def test_empty_input(self):
        config = {"count": 2, "input": "", "distribution": "chunk"}
        with pytest.raises(ValueError, match="no targets to distribute"):
            expand_fleet_to_matrix(config)

    def test_exclusion_integration(self, tmp_path: Path):
        target_file = tmp_path / "targets.txt"
        target_file.write_text("10.0.0.1\n10.0.0.2\n10.0.0.3\n")

        config = {"count": 2, "input": str(target_file), "distribution": "chunk"}
        combos, chunk_files = expand_fleet_to_matrix(config, exclude=["10.0.0.2"])
        try:
            # Only 2 targets after exclusion
            total = sum(c["fleet_target_count"] for c in combos)
            assert total == 2
        finally:
            for f in chunk_files:
                f.unlink(missing_ok=True)
            if chunk_files:
                chunk_files[0].parent.rmdir()

    def test_chunk_files_contain_targets(self, tmp_path: Path):
        target_file = tmp_path / "targets.txt"
        target_file.write_text("10.0.0.1\n10.0.0.2\n")

        config = {"count": 2, "input": str(target_file), "distribution": "chunk"}
        combos, chunk_files = expand_fleet_to_matrix(config)
        try:
            for i, chunk_file in enumerate(chunk_files):
                content = chunk_file.read_text().strip()
                assert content  # Not empty
                lines = content.splitlines()
                assert lines == combos[i]["fleet_input"]
        finally:
            for f in chunk_files:
                f.unlink(missing_ok=True)
            if chunk_files:
                chunk_files[0].parent.rmdir()

    def test_fleet_name_default(self):
        config = {
            "count": 1,
            "input": "10.0.0.1",
            "distribution": "chunk",
        }
        combos, chunk_files = expand_fleet_to_matrix(config)
        try:
            assert "fleet" in combos[0]["fleet_name"]
        finally:
            for f in chunk_files:
                f.unlink(missing_ok=True)
            if chunk_files:
                chunk_files[0].parent.rmdir()
