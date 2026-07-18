"""Tests for FleetInputParser — IP, CIDR, range, hostname parsing and distribution."""

from ofx.cloud.fleet_input import FleetInputParser, split_subnet

class TestParseIP:
    def test_single_ip(self):
        p = FleetInputParser()
        assert p.parse("10.0.0.1") == ["10.0.0.1"]

    def test_multiple_ips_comma_separated(self):
        p = FleetInputParser()
        result = p.parse("10.0.0.1,10.0.0.2,10.0.0.3")
        assert result == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_deduplication(self):
        p = FleetInputParser()
        result = p.parse("10.0.0.1,10.0.0.1,10.0.0.2")
        assert result == ["10.0.0.1", "10.0.0.2"]

    def test_list_input(self):
        p = FleetInputParser()
        result = p.parse(["10.0.0.1", "10.0.0.2"])
        assert result == ["10.0.0.1", "10.0.0.2"]

class TestParseCIDR:
    def test_expand_small_cidr(self):
        p = FleetInputParser(expand_cidrs=True)
        result = p.parse("192.168.1.0/30")
        assert result == ["192.168.1.1", "192.168.1.2"]

    def test_expand_cidr_28(self):
        p = FleetInputParser(expand_cidrs=True)
        result = p.parse("10.0.0.0/28")
        assert len(result) == 14

    def test_no_expand_cidr(self):
        p = FleetInputParser(expand_cidrs=False)
        result = p.parse("192.168.1.0/24")
        assert result == ["192.168.1.0/24"]

    def test_single_host_cidr(self):
        p = FleetInputParser(expand_cidrs=True)
        result = p.parse("10.0.0.5/32")
        assert result == ["10.0.0.5"]

class TestParseRanges:
    def test_full_range(self):
        p = FleetInputParser()
        result = p.parse("10.0.0.1-10.0.0.5")
        assert result == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"]

    def test_short_range(self):
        p = FleetInputParser()
        result = p.parse("10.0.0.1-5")
        assert result == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"]

    def test_reversed_full_range(self):
        p = FleetInputParser()
        result = p.parse("10.0.0.5-10.0.0.1")
        assert len(result) == 5

    def test_reversed_short_range(self):
        p = FleetInputParser()
        result = p.parse("10.0.0.5-1")
        assert len(result) == 5

    def test_single_ip_range(self):
        p = FleetInputParser()
        result = p.parse("10.0.0.1-10.0.0.1")
        assert result == ["10.0.0.1"]

class TestParseHostnames:
    def test_single_hostname(self):
        p = FleetInputParser()
        assert p.parse("target.example.com") == ["target.example.com"]

    def test_mixed_ips_and_hostnames(self):
        p = FleetInputParser()
        result = p.parse(["10.0.0.1", "web.example.com", "192.168.1.1"])
        assert result == ["10.0.0.1", "web.example.com", "192.168.1.1"]

class TestFileInput:
    def test_file_with_ips(self, tmp_path):
        f = tmp_path / "targets.txt"
        f.write_text("10.0.0.1\n10.0.0.2\n10.0.0.3\n")
        p = FleetInputParser()
        result = p.parse(str(f))
        assert result == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_file_with_comments_and_blanks(self, tmp_path):
        f = tmp_path / "targets.txt"
        f.write_text("# Comment\n10.0.0.1\n\n# Another comment\n10.0.0.2\n")
        p = FleetInputParser()
        result = p.parse(str(f))
        assert result == ["10.0.0.1", "10.0.0.2"]

    def test_file_with_mixed_types(self, tmp_path):
        f = tmp_path / "targets.txt"
        f.write_text("10.0.0.1\n192.168.1.0/30\nweb.example.com\n10.0.0.1-3\n")
        p = FleetInputParser(expand_cidrs=True)
        result = p.parse(str(f))
        assert "10.0.0.1" in result
        assert "192.168.1.1" in result
        assert "web.example.com" in result
        assert "10.0.0.2" in result
        assert "10.0.0.3" in result

    def test_recursive_file_loop_detection(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text(f"{f2}\n")
        f2.write_text(f"{f1}\n")
        p = FleetInputParser()
        result = p.parse(str(f1))
        assert isinstance(result, list)

    def test_inline_comments(self, tmp_path):
        f = tmp_path / "targets.txt"
        f.write_text("10.0.0.1 # primary target\n10.0.0.2 # secondary\n")
        p = FleetInputParser()
        result = p.parse(str(f))
        assert result == ["10.0.0.1", "10.0.0.2"]

class TestExclusions:
    def test_exclude_single_ip(self):
        p = FleetInputParser(exclude=["10.0.0.2"])
        result = p.parse("10.0.0.1-5")
        assert "10.0.0.2" not in result
        assert "10.0.0.1" in result

    def test_exclude_cidr(self):
        p = FleetInputParser(exclude=["10.0.0.0/30"])
        result = p.parse("10.0.0.1-10")
        assert "10.0.0.1" not in result
        assert "10.0.0.2" not in result
        assert "10.0.0.3" not in result
        assert "10.0.0.4" in result

    def test_exclude_hostname(self):
        p = FleetInputParser(exclude=["skip.example.com"])
        result = p.parse(["10.0.0.1", "skip.example.com", "keep.example.com"])
        assert "skip.example.com" not in result
        assert "keep.example.com" in result

class TestParsePreservingCIDRs:
    def test_keeps_cidr_intact(self):
        p = FleetInputParser(expand_cidrs=True)
        result = p.parse_preserving_cidrs(["192.168.1.0/24", "10.0.0.1"])
        assert "192.168.1.0/24" in result
        assert "10.0.0.1" in result

    def test_deduplication(self):
        p = FleetInputParser()
        result = p.parse_preserving_cidrs(["10.0.0.1", "10.0.0.1"])
        assert result == ["10.0.0.1"]

class TestDetectType:
    def test_ip(self):
        p = FleetInputParser()
        assert p._detect_type("10.0.0.1") == "ip"

    def test_cidr(self):
        p = FleetInputParser()
        assert p._detect_type("10.0.0.0/24") == "cidr"

    def test_range_full(self):
        p = FleetInputParser()
        assert p._detect_type("10.0.0.1-10.0.0.50") == "range_full"

    def test_range_short(self):
        p = FleetInputParser()
        assert p._detect_type("10.0.0.1-50") == "range_short"

    def test_hostname(self):
        p = FleetInputParser()
        assert p._detect_type("target.example.com") == "hostname"

class TestSplitSubnet:
    def test_split_16_into_4(self):
        result = split_subnet("10.0.0.0/16", 4)
        assert len(result) == 4
        assert "10.0.0.0/18" in result

    def test_split_single(self):
        result = split_subnet("10.0.0.0/24", 1)
        assert result == ["10.0.0.0/24"]

    def test_split_24_into_2(self):
        result = split_subnet("192.168.1.0/24", 2)
        assert len(result) == 2

    def test_split_respects_min_prefix(self):
        result = split_subnet("10.0.0.0/16", 256, min_prefix=24)
        for subnet in result:
            prefix = int(subnet.split("/")[1])
            assert prefix <= 24
