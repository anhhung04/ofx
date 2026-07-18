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
from ofx.utils.file_cleanup import remove_files_and_parent_dir

logger = logging.getLogger("ofx")

def _effective_count(targets: list[str], count: int) -> int:
    if not targets or count <= 0:
        return 0

    effective_count = min(count, len(targets))
    if effective_count < count:
        logger.info(
            "Fleet: reducing instance count from %s to %s (only %s targets)",
            count,
            effective_count,
            len(targets),
        )
    return effective_count

def _write_chunk_files(chunks: list[list[str]]) -> tuple[Path, list[Path]]:
    output_dir = Path(tempfile.mkdtemp(prefix="ofx_fleet_"))
    chunk_files: list[Path] = []
    try:
        for chunk_index, chunk in enumerate(chunks):
            chunk_file = output_dir / f"fleet_chunk_{chunk_index}.txt"
            chunk_file.write_text("\n".join(chunk) + "\n" if chunk else "")
            chunk_files.append(chunk_file)
    except Exception:
        remove_files_and_parent_dir(
            chunk_files,
            on_error=lambda _message: None,
            file_label="chunk file",
            dir_label="chunk dir",
        )
        raise
    return output_dir, chunk_files

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
    """

    def distribute(
        self,
        targets: list[str],
        count: int,
        mode: str = "chunk",
        min_prefix: int = 24,
    ) -> list[list[str]]:
        """Split targets across fleet instances.

        Args:
            targets: List of individual targets (IPs/hostnames).
            count: Number of fleet instances.
            mode: Distribution mode (chunk, round-robin, subnet, line).
            min_prefix: Prefix length used for subnet grouping in ``subnet`` mode.

        Returns:
            List of target lists, one per fleet instance.  Empty lists are
            never returned — if there are no targets the result is ``[]``
            (no instances at all).
        """
        effective_count = _effective_count(targets, count)
        if effective_count == 0:
            return []

        return [
            chunk
            for chunk in self._distribute_mode(targets, effective_count, mode, min_prefix)
            if chunk
        ]

    def _distribute_mode(
        self,
        targets: list[str],
        effective_count: int,
        mode: str,
        min_prefix: int,
    ) -> list[list[str]]:
        match mode:
            case "chunk":
                return self._chunk(targets, effective_count)
            case "round-robin":
                return self._round_robin(targets, effective_count)
            case "subnet":
                return self._subnet_aware(targets, effective_count, min_prefix)
            case "line":
                return [[target] for target in targets]
            case _:
                logger.warning("Unknown distribution mode '%s', using chunk", mode)
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

    def _subnet_aware(
        self, targets: list[str], count: int, min_prefix: int = 24
    ) -> list[list[str]]:
        """Group targets by subnet, then distribute groups across instances.

        Keeps IPs from the same subnet together in the same chunk.

        Args:
            targets: List of individual targets.
            count: Number of instances to distribute across.
            min_prefix: Prefix length for subnet grouping (default /24).
        """
        subnet_groups: dict[str, list[str]] = {}
        ungrouped: list[str] = []

        for target in targets:
            try:
                addr = ipaddress.ip_address(target)
            except ValueError:
                ungrouped.append(target)
                continue
            group_key = str(ipaddress.ip_network(f"{addr}/{min_prefix}", strict=False))
            subnet_groups.setdefault(group_key, []).append(target)

        sorted_groups = sorted(subnet_groups.values(), key=len, reverse=True)
        if ungrouped:
            sorted_groups.append(ungrouped)

        buckets: list[list[str]] = [[] for _ in range(count)]
        bucket_sizes = [0] * count

        for group in sorted_groups:
            bucket_index = bucket_sizes.index(min(bucket_sizes))
            buckets[bucket_index].extend(group)
            bucket_sizes[bucket_index] += len(group)

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

    Note:
        On failure, any partially written chunk files are removed before
        the exception propagates.
    """
    count = fleet_config.get("count", 1)
    input_data = fleet_config.get("input", "")
    distribution = fleet_config.get("distribution", "chunk")
    min_prefix = fleet_config.get("min_prefix", 24)
    exclude_list = fleet_config.get("exclude", []) or []
    if exclude:
        exclude_list.extend(exclude)

    parser = FleetInputParser(expand_cidrs=expand_cidrs, exclude=exclude_list)
    distributor = FleetDistributor()

    targets = parser.parse(input_data) if input_data else []

    if not targets:
        raise ValueError(
            f"Fleet: no targets to distribute. "
            f"Check that 'input' is set and contains valid IPs, CIDRs, hostnames, "
            f"or file paths (got input={input_data!r})."
        )

    chunks = distributor.distribute(targets, count, distribution, min_prefix)

    if not chunks:
        raise ValueError(
            f"Fleet: distribution produced no chunks (count={count}). "
            f"Ensure 'count' is at least 1."
        )

    output_dir, chunk_files = _write_chunk_files(chunks)

    logger.debug(
        f"Fleet: distributed {len(targets)} targets across {len(chunk_files)} "
        f"chunk files in {output_dir}"
    )

    fleet_total = len(chunks)
    return [
        {
            "fleet_index": chunk_index,
            "fleet_total": fleet_total,
            "fleet_input_file": str(chunk_files[chunk_index]),
            "fleet_target_count": len(chunk),
            "fleet_input": chunk,
            "fleet_name": f"[{fleet_config.get('name', 'fleet')}]{{{chunk_index}}}",
        }
        for chunk_index, chunk in enumerate(chunks)
    ], chunk_files
