"""Fleet input parser for network-aware target splitting.

Parses IPs, CIDRs, IP ranges, hostnames from files/strings,
expands them to individual targets for fleet distribution.
"""

from __future__ import annotations

import ipaddress
import logging
import math
import re
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path

logger = logging.getLogger("ofx")

# Pattern for IP ranges like 10.0.0.1-10.0.0.50 or 10.0.0.1-50
_RANGE_FULL = re.compile(
    r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*-\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$"
)
_RANGE_SHORT = re.compile(r"^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{1,3})\s*-\s*(\d{1,3})$")


class FleetInputParser:
    """Parses and expands fleet input into distributable targets.

    Supports:
    - Individual IPs: 10.0.0.1
    - CIDR subnets: 192.168.1.0/24
    - IP ranges: 10.0.0.1-10.0.0.50 or 10.0.0.1-50
    - Hostnames: target.example.com
    - Files with mixed content (one target per line)
    - Inline lists
    - Comments (# ...) and blank lines are ignored

    Example:
        parser = FleetInputParser(expand_cidrs=True)
        targets = parser.parse("targets.txt")
        targets = parser.parse("10.0.0.0/24")
        targets = parser.parse(["10.0.0.1", "192.168.1.0/24"])
    """

    def __init__(
        self,
        expand_cidrs: bool = True,
        exclude: list[str] | None = None,
    ):
        self.expand_cidrs = expand_cidrs
        self._exclude_nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        self._exclude_ips: set[str] = set()

        if exclude:
            for item in exclude:
                self._register_exclusion(item)

    def _register_exclusion(self, item: str) -> None:
        try:
            net = ipaddress.ip_network(item, strict=False)
        except ValueError:
            self._exclude_ips.add(item)
            return

        if net.prefixlen == net.max_prefixlen:
            self._exclude_ips.add(str(net.network_address))
            return
        self._exclude_nets.append(net)

    def parse(self, input_data: str | list[str]) -> list[str]:
        """Parse input and return a flat list of targets.

        Args:
            input_data: File path, CIDR, IP, comma-separated, or list.

        Returns:
            Deduplicated list of individual targets (IPs or hostnames).
        """
        raw_lines = self._read_input(input_data)
        targets: list[str] = []
        seen: set[str] = set()

        for line in raw_lines:
            for target in self._expand_line(line):
                if target not in seen and not self._is_excluded(target):
                    seen.add(target)
                    targets.append(target)

        if not targets:
            logger.warning("Fleet input parser produced 0 targets")

        total = len(targets)
        if total > 1_000_000:
            logger.warning(
                f"Fleet input expanded to {total:,} targets. "
                "This may consume significant memory."
            )

        return targets

    def parse_preserving_cidrs(self, input_data: str | list[str]) -> list[str]:
        """Parse input but keep CIDRs as-is (don't expand to individual IPs).

        Useful for tools that natively accept CIDR notation (e.g., masscan).
        """
        raw_lines = self._read_input(input_data)
        targets: list[str] = []
        seen: set[str] = set()

        for line in raw_lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line not in seen:
                seen.add(line)
                targets.append(line)

        return targets

    def _read_input(
        self, input_data: str | list[str], _seen_files: set[str] | None = None
    ) -> list[str]:
        """Read input into a list of raw lines, supporting recursive file inclusion."""
        if _seen_files is None:
            _seen_files = set()

        if isinstance(input_data, list):
            lines: list[str] = []
            for item in input_data:
                lines.extend(self._read_input(str(item), _seen_files))
            return lines

        input_str = input_data.strip()
        path = Path(input_str)
        cwd_path = Path.cwd() / input_str
        file_to_read: Path | None = None
        if path.is_absolute() and path.is_file():
            file_to_read = path
        elif cwd_path.is_file():
            file_to_read = cwd_path
        elif path.is_file():
            file_to_read = path

        if file_to_read is None:
            if "," in input_str and "/" not in input_str.split(",")[0]:
                return [item.strip() for item in input_str.split(",")]
            return input_str.splitlines()

        abs_path = str(file_to_read.resolve())
        if abs_path in _seen_files:
            logger.warning(
                f"Recursive fleet input: already read file {abs_path}, skipping to avoid loop."
            )
            return []

        _seen_files.add(abs_path)
        logger.debug(f"Reading fleet input from file: {file_to_read}")

        expanded_lines: list[str] = []
        for line in file_to_read.read_text().splitlines():
            normalized = line.strip()
            if not normalized or normalized.startswith("#"):
                continue

            possible_path = Path(normalized)
            nested_path = (
                possible_path if possible_path.is_absolute() else Path.cwd() / normalized
            )
            if nested_path.is_file():
                expanded_lines.extend(self._read_input(normalized, _seen_files))
            else:
                expanded_lines.append(normalized)
        return expanded_lines

    def _expand_line(self, line: str) -> Iterator[str]:
        """Expand a single line into individual targets."""
        line = line.strip()
        if not line or line.startswith("#"):
            return

        # Remove inline comments
        if "#" in line:
            line = line[: line.index("#")].strip()

        line_type = self._detect_type(line)

        match line_type:
            case "cidr":
                if self.expand_cidrs:
                    yield from self._expand_cidr(line)
                else:
                    yield line
            case "range_full":
                yield from self._expand_range_full(line)
            case "range_short":
                yield from self._expand_range_short(line)
            case "ip" | "hostname":
                yield line

    def _detect_type(self, line: str) -> str:
        """Detect the type of a target line."""
        if _RANGE_FULL.match(line):
            return "range_full"
        if _RANGE_SHORT.match(line):
            return "range_short"
        if "/" in line:
            with suppress(ValueError):
                ipaddress.ip_network(line, strict=False)
                return "cidr"
        with suppress(ValueError):
            ipaddress.ip_address(line)
            return "ip"
        return "hostname"

    def _expand_cidr(self, cidr: str) -> Iterator[str]:
        """Expand CIDR to individual host IPs."""
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            yield cidr
            return

        if network.prefixlen == network.max_prefixlen:
            yield str(network.network_address)
            return

        for ip in network.hosts():
            yield str(ip)

    def _expand_range_full(self, range_str: str) -> Iterator[str]:
        """Expand 10.0.0.1-10.0.0.50 to individual IPs."""
        match = _RANGE_FULL.match(range_str)
        if not match:
            yield range_str
            return

        try:
            start = ipaddress.ip_address(match.group(1))
            end = ipaddress.ip_address(match.group(2))
        except ValueError:
            yield range_str
            return

        if int(end) < int(start):
            start, end = end, start

        for i in range(int(start), int(end) + 1):
            yield str(ipaddress.ip_address(i))

    def _expand_range_short(self, range_str: str) -> Iterator[str]:
        """Expand 10.0.0.1-50 to individual IPs (short range notation)."""
        match = _RANGE_SHORT.match(range_str)
        if not match:
            yield range_str
            return

        prefix = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3))

        if end < start:
            start, end = end, start

        # Validate octet range
        if start > 255 or end > 255:
            logger.warning(
                "IP range '%s' contains invalid octets (>255); skipping", range_str
            )
            return

        for i in range(start, end + 1):
            yield f"{prefix}.{i}"

    def _is_excluded(self, target: str) -> bool:
        """Check if a target is in the exclusion list."""
        if target in self._exclude_ips:
            return True
        try:
            addr = ipaddress.ip_address(target)
            for net in self._exclude_nets:
                if addr in net:
                    return True
        except ValueError:
            return False
        return False


def split_subnet(cidr: str, count: int, min_prefix: int = 32) -> list[str]:
    """Split a CIDR into sub-subnets for distribution.

    Tries to split into `count` equal-ish sub-subnets on CIDR boundaries.

    Args:
        cidr: Network in CIDR notation (e.g., "10.0.0.0/16").
        count: Number of chunks to split into.
        min_prefix: Minimum prefix length (e.g., 24 to stop at /24).

    Returns:
        List of CIDR strings.

    Example:
        >>> split_subnet("10.0.0.0/16", 4)
        ['10.0.0.0/18', '10.0.64.0/18', '10.0.128.0/18', '10.0.192.0/18']
    """
    network = ipaddress.ip_network(cidr, strict=False)

    if count <= 1:
        return [str(network)]

    # Calculate prefix for splitting
    extra_bits = math.ceil(math.log2(count))
    new_prefix = network.prefixlen + extra_bits

    if new_prefix > min_prefix:
        new_prefix = min_prefix
    if new_prefix > network.max_prefixlen:
        new_prefix = network.max_prefixlen

    subnets = list(network.subnets(new_prefix=new_prefix))

    # If we generated more subnets than needed, group them
    if len(subnets) > count:
        # Merge surplus subnets into the last groups
        result = []
        chunk_size = len(subnets) // count
        remainder = len(subnets) % count
        start = 0
        for i in range(count):
            end = start + chunk_size + (1 if i < remainder else 0)
            group = subnets[start:end]
            if len(group) == 1:
                result.append(str(group[0]))
            else:
                # Return individual subnets in the group
                result.extend(str(s) for s in group)
            start = end
        return result[:count] if len(result) > count else result

    return [str(s) for s in subnets]
