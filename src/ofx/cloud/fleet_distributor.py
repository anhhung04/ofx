"""Fleet distributor for splitting targets across fleet instances.

Takes a list of targets (from FleetInputParser) and distributes
them across N fleet instances using various strategies.
"""

from __future__ import annotations

import ipaddress
import logging
import tempfile
from pathlib import Path
from typing import Any

from ofx.cloud.fleet_input import FleetInputParser

logger = logging.getLogger("ofx")


class FleetDistributor:
    """Distributes targets across fleet instances.

    Modes:
    - chunk: Split into N contiguous chunks (default)
    - round-robin: Deal targets one-by-one across instances
    - subnet: Keep targets from same original subnet together
    - line: One target per instance (count = target count)

    Example:
        distributor = FleetDistributor()
        chunks = distributor.distribute(targets, count=10, mode="chunk")
        # chunks[0] = ["10.0.0.1", "10.0.0.2", ...] for instance 0
    """

    def distribute(
        self,
        targets: list[str],
        count: int,
        mode: str = "chunk",
    ) -> list[list[str]]:
        """Split targets across fleet instances.

        Args:
            targets: List of individual targets (IPs/hostnames).
            count: Number of fleet instances.
            mode: Distribution mode (chunk, round-robin, subnet, line).

        Returns:
            List of target lists, one per fleet instance.
            Empty instances are removed (fleet count may be reduced).
        """
        if not targets:
            return [[] for _ in range(count)]

        # Reduce count if we have fewer targets than instances
        effective_count = min(count, len(targets))
        if effective_count < count:
            logger.info(
                f"Fleet: reducing instance count from {count} to {effective_count} "
                f"(only {len(targets)} targets)"
            )

        match mode:
            case "chunk":
                return self._chunk(targets, effective_count)
            case "round-robin":
                return self._round_robin(targets, effective_count)
            case "subnet":
                return self._subnet_aware(targets, effective_count)
            case "line":
                return [[t] for t in targets]
            case _:
                logger.warning(f"Unknown distribution mode '{mode}', using chunk")
                return self._chunk(targets, effective_count)

    def _chunk(self, targets: list[str], count: int) -> list[list[str]]:
        """Split into N contiguous chunks."""
        if count <= 0:
            return []
        chunk_size = len(targets) // count
        remainder = len(targets) % count
        chunks: list[list[str]] = []
        start = 0
        for i in range(count):
            end = start + chunk_size + (1 if i < remainder else 0)
            chunks.append(targets[start:end])
            start = end
        return chunks

    def _round_robin(self, targets: list[str], count: int) -> list[list[str]]:
        """Distribute one-by-one across instances."""
        buckets: list[list[str]] = [[] for _ in range(count)]
        for i, target in enumerate(targets):
            buckets[i % count].append(target)
        return buckets

    def _subnet_aware(self, targets: list[str], count: int) -> list[list[str]]:
        """Group targets by /24 subnet, then distribute groups across instances.

        Keeps IPs from the same subnet together in the same chunk.
        """
        # Group by /24 subnet
        subnet_groups: dict[str, list[str]] = {}
        ungrouped: list[str] = []

        for target in targets:
            try:
                addr = ipaddress.ip_address(target)
                # Group by /24
                net = ipaddress.ip_network(f"{addr}/24", strict=False)
                key = str(net)
                if key not in subnet_groups:
                    subnet_groups[key] = []
                subnet_groups[key].append(target)
            except ValueError:
                # Hostname or invalid IP — can't group
                ungrouped.append(target)

        # Sort groups by size (largest first) for better distribution
        sorted_groups = sorted(subnet_groups.values(), key=len, reverse=True)
        if ungrouped:
            sorted_groups.append(ungrouped)

        # Distribute groups to buckets (greedy: assign to least-full bucket)
        buckets: list[list[str]] = [[] for _ in range(count)]
        bucket_sizes = [0] * count

        for group in sorted_groups:
            # Find the least-full bucket
            min_idx = bucket_sizes.index(min(bucket_sizes))
            buckets[min_idx].extend(group)
            bucket_sizes[min_idx] += len(group)

        return buckets


def expand_fleet_to_matrix(
    fleet_config: dict[str, Any],
    expand_cidrs: bool = True,
    exclude: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Expand a fleet strategy config into matrix combinations.

    This is the bridge between fleet config and MatrixJobRunner.
    Generates matrix combinations with fleet context variables.

    Args:
        fleet_config: Fleet strategy dict with count, input, distribution, etc.
        expand_cidrs: Whether to expand CIDRs to individual IPs.
        exclude: IPs/CIDRs to exclude.

    Returns:
        Tuple of (matrix_combinations, chunk_files):
        - matrix_combinations: list of dicts with fleet.* context
        - chunk_files: list of Path objects for chunk files
    """
    count = fleet_config.get("count", 1)
    input_data = fleet_config.get("input", "")
    distribution = fleet_config.get("distribution", "chunk")
    exclude_list = fleet_config.get("exclude", []) or []
    if exclude:
        exclude_list.extend(exclude)

    parser = FleetInputParser(expand_cidrs=expand_cidrs, exclude=exclude_list)
    distributor = FleetDistributor()

    # Parse targets
    targets = parser.parse(input_data) if input_data else []

    # Distribute once, then write chunk files from the result
    chunks = distributor.distribute(targets, count, distribution)

    output_dir = Path(tempfile.mkdtemp(prefix="ofx_fleet_"))
    chunk_files: list[Path] = []
    for i, chunk in enumerate(chunks):
        chunk_file = output_dir / f"fleet_chunk_{i}.txt"
        chunk_file.write_text("\n".join(chunk) + "\n" if chunk else "")
        chunk_files.append(chunk_file)

    logger.debug(
        f"Fleet: distributed {len(targets)} targets across {len(chunk_files)} "
        f"chunk files in {output_dir}"
    )

    # Build matrix combinations
    combinations = []
    for i, chunk in enumerate(chunks):
        combo = {
            "fleet_index": i,
            "fleet_total": len(chunks),
            "fleet_input_file": str(chunk_files[i]),
            "fleet_target_count": len(chunk),
            "fleet_input": chunk,
            "fleet_name": f"[{fleet_config.get('name', 'fleet')}]{{{i}}}",
        }
        combinations.append(combo)

    return combinations, chunk_files
