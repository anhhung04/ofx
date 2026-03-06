"""Tests for CloudMatrixJobRunner — cloud+matrix and cloud+fleet expansion."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest

from ofx.models.strategy import FleetStrategy, MatrixStrategy


class TestCloudMatrixCombinationExpansion:
    """Test the combination building logic without actual cloud provisioning."""

    def _make_runner(self, strategy: MatrixStrategy | None = None):
        """Create a CloudMatrixJobRunner with stubbed parent/context."""
        from ofx.models.job import Job
        from ofx.runner.core import RunContext
        from ofx.runner.execution.cloud_job import CloudMatrixJobRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )

        # Minimal parent stub
        class _ParentStub:
            model = type("W", (), {"name": "test-wf"})()
            runners = {}
            _runners = {}

            def _produce_log(self, msg):
                return msg

        parent = _ParentStub()
        ctx = RunContext()
        runner = CloudMatrixJobRunner(job, ctx, parent=parent)  # type: ignore
        return runner

    def test_matrix_only_expansion(self):
        """Cloud + matrix with no fleet."""
        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"], "mode": ["fast", "thorough"]},
        )
        runner = self._make_runner(strategy)
        combos = runner._build_combinations()

        # 2 tools × 2 modes = 4 combinations
        assert len(combos) == 4
        # Each combo should have 'tool' and 'mode' keys
        for c in combos:
            assert "tool" in c
            assert "mode" in c

    def test_matrix_with_exclude(self):
        """Matrix expansion with exclude filter."""
        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"], "mode": ["fast", "thorough"]},
            exclude=[{"tool": "masscan", "mode": "thorough"}],
        )
        runner = self._make_runner(strategy)
        combos = runner._build_combinations()

        # 4 base - 1 excluded = 3
        assert len(combos) == 3
        assert {"tool": "masscan", "mode": "thorough"} not in combos

    def test_matrix_with_include(self):
        """Matrix expansion with extra include."""
        strategy = MatrixStrategy(
            matrix={"tool": ["nmap"]},
            include=[{"tool": "nuclei"}],
        )
        runner = self._make_runner(strategy)
        combos = runner._build_combinations()

        assert len(combos) == 2
        assert {"tool": "nmap"} in combos
        assert {"tool": "nuclei"} in combos

    def test_fleet_only_expansion(self, tmp_path):
        """Cloud + fleet with no matrix."""
        # Create a targets file
        targets = tmp_path / "targets.txt"
        targets.write_text("10.0.0.1\n10.0.0.2\n10.0.0.3\n10.0.0.4\n")

        strategy = MatrixStrategy(
            fleet=FleetStrategy(
                count=2,
                input=str(targets),
                distribution="chunk",
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._build_combinations()

        assert len(combos) == 2
        for c in combos:
            assert "fleet_index" in c
            assert "fleet_total" in c
            assert "fleet_input_file" in c
            assert "fleet_target_count" in c
        assert combos[0]["fleet_index"] == 0
        assert combos[1]["fleet_index"] == 1
        assert combos[0]["fleet_total"] == 2
        # Verify chunk files were created
        assert len(runner._chunk_files) == 2
        for f in runner._chunk_files:
            assert Path(f).exists()

        # Cleanup
        runner._cleanup_chunk_files()

    def test_matrix_and_fleet_cartesian(self, tmp_path):
        """Cloud + matrix + fleet → Cartesian product."""
        targets = tmp_path / "targets.txt"
        targets.write_text("10.0.0.1\n10.0.0.2\n10.0.0.3\n")

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"]},
            fleet=FleetStrategy(
                count=3,
                input=str(targets),
                distribution="chunk",
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._build_combinations()

        # 2 tools × 3 fleet chunks = 6
        assert len(combos) == 6
        for c in combos:
            assert "tool" in c
            assert "fleet_index" in c
            assert "fleet_input_file" in c

        # Cleanup
        runner._cleanup_chunk_files()

    def test_empty_strategy(self):
        """No matrix or fleet → single empty combo."""
        strategy = MatrixStrategy()
        runner = self._make_runner(strategy)
        combos = runner._build_combinations()
        assert combos == [{}]

    def test_no_strategy(self):
        """None strategy → single empty combo."""
        runner = self._make_runner(None)
        combos = runner._build_combinations()
        assert combos == [{}]

    def test_fleet_cleanup(self, tmp_path):
        """Chunk files are cleaned up after _post_run / _cleanup_chunk_files."""
        targets = tmp_path / "targets.txt"
        targets.write_text("a\nb\nc\nd\n")

        strategy = MatrixStrategy(
            fleet=FleetStrategy(count=2, input=str(targets)),
        )
        runner = self._make_runner(strategy)
        runner._build_combinations()

        # Files exist
        assert all(Path(f).exists() for f in runner._chunk_files)

        runner._cleanup_chunk_files()

        # Files cleaned up
        assert runner._chunk_files == []

    def test_fleet_ip_input(self):
        """Fleet with inline IP list."""
        strategy = MatrixStrategy(
            fleet=FleetStrategy(
                count=2,
                input="10.0.0.1,10.0.0.2,10.0.0.3,10.0.0.4",
                distribution="round-robin",
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._build_combinations()

        assert len(combos) == 2
        assert combos[0]["fleet_target_count"] == 2
        assert combos[1]["fleet_target_count"] == 2

        runner._cleanup_chunk_files()

    def test_fleet_reduces_count_when_few_targets(self):
        """Fleet count reduced when fewer targets than instances."""
        strategy = MatrixStrategy(
            fleet=FleetStrategy(
                count=10,
                input="10.0.0.1,10.0.0.2",
            ),
        )
        runner = self._make_runner(strategy)
        combos = runner._build_combinations()

        # Only 2 targets → reduced to 2 instances
        assert len(combos) == 2
        runner._cleanup_chunk_files()
