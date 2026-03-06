"""Tests for cloud runner classes — CloudFleetRunner and CloudMatrixJobRunner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ofx.models.strategy import FleetStrategy, MatrixStrategy


class TestCloudFleetRunner:
    """Test the fleet expansion logic in CloudFleetRunner."""

    def _make_runner(self, strategy: MatrixStrategy | None = None):
        """Create a CloudFleetRunner with stubbed parent/context."""
        from ofx.models.job import Job
        from ofx.runner.core import RunContext
        from ofx.runner.execution.cloud_fleet import CloudFleetRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )

        class _ParentStub:
            model = type("W", (), {"name": "test-wf"})()
            runners = {}
            _runners = {}

            def _produce_log(self, msg):
                return msg

        parent = _ParentStub()
        ctx = RunContext()
        runner = CloudFleetRunner(job, ctx, parent=parent)  # type: ignore
        return runner

    def test_fleet_only_expansion(self, tmp_path):
        """Cloud + fleet with no matrix."""
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
        combos = runner._expand_fleet()

        assert len(combos) == 2
        for c in combos:
            assert "fleet_index" in c
            assert "fleet_total" in c
            assert "fleet_input_file" in c
            assert "fleet_target_count" in c
        assert combos[0]["fleet_index"] == 0
        assert combos[1]["fleet_index"] == 1
        assert combos[0]["fleet_total"] == 2
        assert len(runner._chunk_files) == 2
        for f in runner._chunk_files:
            assert Path(f).exists()

        runner._cleanup_chunk_files()

    def test_fleet_with_matrix_expansion(self, tmp_path):
        """Cloud + matrix + fleet → fleet chunks only (matrix on each VPS)."""
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
        combos = runner._expand_fleet()

        # 3 fleet chunks (matrix combos are handled by CloudMatrixJobRunner)
        assert len(combos) == 3
        for c in combos:
            assert "fleet_index" in c
            assert "fleet_input_file" in c

        runner._cleanup_chunk_files()

    def test_no_fleet_returns_default(self):
        """No fleet → single empty combo."""
        strategy = MatrixStrategy()
        runner = self._make_runner(strategy)
        combos = runner._expand_fleet()
        assert combos == [{}]

    def test_fleet_cleanup(self, tmp_path):
        """Chunk files are cleaned up after _cleanup_chunk_files."""
        targets = tmp_path / "targets.txt"
        targets.write_text("a\nb\nc\nd\n")

        strategy = MatrixStrategy(
            fleet=FleetStrategy(count=2, input=str(targets)),
        )
        runner = self._make_runner(strategy)
        runner._expand_fleet()

        assert all(Path(f).exists() for f in runner._chunk_files)

        runner._cleanup_chunk_files()
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
        combos = runner._expand_fleet()

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
        combos = runner._expand_fleet()

        # Only 2 targets → reduced to 2 instances
        assert len(combos) == 2
        runner._cleanup_chunk_files()


class TestCloudMatrixExpansion:
    """Test the matrix expansion logic in CloudMatrixJobRunner."""

    def test_matrix_expansion(self):
        """CloudMatrixJobRunner._expand_matrix produces correct combos."""
        from ofx.models.job import Job
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"], "mode": ["fast", "thorough"]},
        )
        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )
        # We only test the expansion helper, no need for real parent
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = runner._expand_matrix()

        assert len(combos) == 4
        for c in combos:
            assert "tool" in c
            assert "mode" in c

    def test_matrix_with_exclude(self):
        """Matrix expansion with exclude filter."""
        from ofx.models.job import Job
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap", "masscan"], "mode": ["fast", "thorough"]},
            exclude=[{"tool": "masscan", "mode": "thorough"}],
        )
        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = runner._expand_matrix()

        assert len(combos) == 3
        assert {"tool": "masscan", "mode": "thorough"} not in combos

    def test_matrix_with_include(self):
        """Matrix expansion with extra include."""
        from ofx.models.job import Job
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        strategy = MatrixStrategy(
            matrix={"tool": ["nmap"]},
            include=[{"tool": "nuclei"}],
        )
        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=strategy,
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = runner._expand_matrix()

        assert len(combos) == 2
        assert {"tool": "nmap"} in combos
        assert {"tool": "nuclei"} in combos

    def test_no_matrix_returns_empty(self):
        """No matrix → empty list."""
        from ofx.models.job import Job
        from ofx.runner.execution.cloud_matrix import CloudMatrixJobRunner

        job = Job(
            jid="test-job",
            cloud={"provider": "static", "host": "10.0.0.1"},
            strategy=MatrixStrategy(),
            steps=[{"run": "echo hi"}],
        )
        runner = CloudMatrixJobRunner.__new__(CloudMatrixJobRunner)
        runner.model = job
        combos = runner._expand_matrix()
        assert combos == []
