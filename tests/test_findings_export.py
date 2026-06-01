"""Tests for the findings auto-export module."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from ofx.runner.findings_export import (
    collect_typed_outputs,
    export_typed_outputs,
)
from ofx.runner.target_paths import sanitize_target_slug


# ── export_typed_outputs ──────────────────────────────────────────


class TestExportTypedOutputs:
    def test_empty_list_returns_empty(self, tmp_path):
        assert export_typed_outputs(str(tmp_path), []) == []

    def test_empty_project_path_returns_empty(self):
        assert export_typed_outputs("", [{"_type": "subdomain", "host": "x"}]) == []

    def test_none_project_path_returns_empty(self):
        assert export_typed_outputs(None, [{"_type": "subdomain", "host": "x"}]) == []

    def test_exports_subdomains(self, tmp_path):
        items = [
            {"_type": "subdomain", "host": "a.example.com"},
            {"_type": "subdomain", "host": "b.example.com"},
        ]
        summaries = export_typed_outputs(str(tmp_path), items)
        assert len(summaries) == 1
        assert "subdomains/subdomains.txt" in summaries[0]
        assert "(2 items)" in summaries[0]

        content = (tmp_path / "subdomains" / "subdomains.txt").read_text()
        lines = content.strip().splitlines()
        assert "a.example.com" in lines
        assert "b.example.com" in lines
        assert lines == sorted(lines)

    def test_exports_urls(self, tmp_path):
        items = [
            {"_type": "url", "url": "https://example.com/login"},
            {"_type": "url", "url": "https://example.com/admin"},
        ]
        summaries = export_typed_outputs(str(tmp_path), items)
        assert len(summaries) == 1
        assert "web/urls.txt" in summaries[0]

        content = (tmp_path / "web" / "urls.txt").read_text()
        lines = content.strip().splitlines()
        assert len(lines) == 2

    def test_exports_ports(self, tmp_path):
        items = [
            {"_type": "port", "ip": "10.0.0.1", "port": 80},
            {"_type": "port", "ip": "10.0.0.1", "port": 443},
        ]
        _summaries = export_typed_outputs(str(tmp_path), items)
        content = (tmp_path / "hosts" / "ports.txt").read_text()
        assert "10.0.0.1:80" in content
        assert "10.0.0.1:443" in content

    def test_exports_vulnerabilities_as_jsonl(self, tmp_path):
        items = [
            {
                "_type": "vulnerability",
                "name": "XSS",
                "severity": "high",
                "url": "https://x.com",
            },
            {
                "_type": "vulnerability",
                "name": "SQLi",
                "severity": "critical",
                "url": "https://y.com",
            },
        ]
        summaries = export_typed_outputs(str(tmp_path), items)
        assert "vulns/vulnerabilities.jsonl" in summaries[0]

        content = (tmp_path / "vulns" / "vulnerabilities.jsonl").read_text()
        lines = content.strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert obj["_type"] == "vulnerability"

    def test_deduplicates_text(self, tmp_path):
        items = [
            {"_type": "subdomain", "host": "a.example.com"},
            {"_type": "subdomain", "host": "a.example.com"},
            {"_type": "subdomain", "host": "b.example.com"},
        ]
        export_typed_outputs(str(tmp_path), items)
        content = (tmp_path / "subdomains" / "subdomains.txt").read_text()
        lines = content.strip().splitlines()
        assert len(lines) == 2

    def test_jsonl_export_serializes_with_default_str(self, tmp_path):
        export_typed_outputs(
            str(tmp_path),
            [
                {"_type": "vulnerability", "ok": 1},
                {"_type": "vulnerability", "name": object()},
            ],
        )

        lines = (tmp_path / "vulns" / "vulnerabilities.jsonl").read_text().splitlines()
        assert lines[0] == '{"_type": "vulnerability", "ok": 1}'
        assert len(lines) == 2

    def test_text_export_collects_unique_values_and_skips_blank_existing_lines(self, tmp_path):
        fpath = tmp_path / "subdomains" / "subdomains.txt"
        fpath.parent.mkdir(parents=True)
        fpath.write_text("a.example.com\n\n b.example.com \n")

        export_typed_outputs(
            str(tmp_path),
            [
                {"_type": "subdomain", "host": "a.example.com"},
                {"_type": "subdomain", "host": "a.example.com"},
                {"_type": "subdomain", "host": "b.example.com"},
            ],
        )

        assert set(fpath.read_text().splitlines()) == {"a.example.com", " b.example.com ", "b.example.com"}

    def test_export_typed_outputs_adds_prefix_and_summary_label(self, tmp_path):
        summary = export_typed_outputs(
            str(tmp_path),
            [
                {"_type": "subdomain", "host": "a.example.com"},
                {"_type": "subdomain", "host": "a.example.com"},
                {"_type": "subdomain", "host": "b.example.com"},
            ],
            prefix="domain-scan",
        )[0]

        assert summary == "  [+] subdomains/domain-scan-subdomains.txt (3 items, 2 new)"

    def test_export_typed_outputs_returns_summary_for_target_path(self, tmp_path):
        summary = export_typed_outputs(
            str(tmp_path),
            [{"_type": "subdomain", "host": "a.example.com", "_target": "example.com"}],
            prefix="scan",
        )[1]

        assert summary == "  [+] subdomains/example.com/scan-subdomains.txt (1 items)"
        assert (tmp_path / "subdomains" / "example.com" / "scan-subdomains.txt").exists()

    def test_sanitize_target_slug_strips_url_path_and_collapses_separators(self):
        assert sanitize_target_slug("https://example.com:8443/path") == "example.com_8443"
        assert sanitize_target_slug("api///v1") == "api_v1"

    def test_deduplicates_jsonl(self, tmp_path):
        item = {"_type": "vulnerability", "name": "XSS", "url": "https://x.com"}
        export_typed_outputs(str(tmp_path), [item])
        export_typed_outputs(str(tmp_path), [item])  # Second call with same item
        content = (tmp_path / "vulns" / "vulnerabilities.jsonl").read_text()
        lines = content.strip().splitlines()
        assert len(lines) == 1

    def test_appends_to_existing_text(self, tmp_path):
        items1 = [{"_type": "subdomain", "host": "a.example.com"}]
        items2 = [{"_type": "subdomain", "host": "b.example.com"}]
        export_typed_outputs(str(tmp_path), items1)
        export_typed_outputs(str(tmp_path), items2)
        content = (tmp_path / "subdomains" / "subdomains.txt").read_text()
        lines = content.strip().splitlines()
        assert len(lines) == 2

    def test_appends_to_existing_jsonl(self, tmp_path):
        items1 = [{"_type": "vulnerability", "name": "XSS"}]
        items2 = [{"_type": "vulnerability", "name": "SQLi"}]
        export_typed_outputs(str(tmp_path), items1)
        export_typed_outputs(str(tmp_path), items2)
        content = (tmp_path / "vulns" / "vulnerabilities.jsonl").read_text()
        lines = content.strip().splitlines()
        assert len(lines) == 2

    def test_mixed_types(self, tmp_path):
        items = [
            {"_type": "subdomain", "host": "sub.example.com"},
            {"_type": "url", "url": "https://example.com"},
            {"_type": "port", "ip": "10.0.0.1", "port": 22},
            {"_type": "tag", "name": "Nginx"},
        ]
        summaries = export_typed_outputs(str(tmp_path), items)
        assert len(summaries) == 4
        assert (tmp_path / "subdomains" / "subdomains.txt").exists()
        assert (tmp_path / "web" / "urls.txt").exists()
        assert (tmp_path / "hosts" / "ports.txt").exists()
        assert (tmp_path / "web" / "tags.txt").exists()

    def test_prefix_modifies_filename(self, tmp_path):
        items = [{"_type": "subdomain", "host": "a.example.com"}]
        export_typed_outputs(str(tmp_path), items, prefix="domain-scan")
        assert (tmp_path / "subdomains" / "domain-scan-subdomains.txt").exists()

    def test_skips_non_dict_items(self, tmp_path):
        items = [
            {"_type": "subdomain", "host": "a.example.com"},
            "not a dict",
            42,
            None,
        ]
        summaries = export_typed_outputs(str(tmp_path), items)
        assert len(summaries) == 1

    def test_skips_items_without_type(self, tmp_path):
        items = [
            {"host": "a.example.com"},  # No _type
            {"_type": "subdomain", "host": "b.example.com"},
        ]
        summaries = export_typed_outputs(str(tmp_path), items)
        assert len(summaries) == 1
        content = (tmp_path / "subdomains" / "subdomains.txt").read_text()
        assert "b.example.com" in content

    def test_unknown_type_goes_to_scans(self, tmp_path):
        items = [{"_type": "custom_thing", "data": "value"}]
        summaries = export_typed_outputs(str(tmp_path), items)
        assert "scans/custom_thing.txt" in summaries[0]

    def test_creates_directories(self, tmp_path):
        project = tmp_path / "deep" / "nested" / "project"
        items = [{"_type": "subdomain", "host": "a.example.com"}]
        export_typed_outputs(str(project), items)
        assert (project / "subdomains" / "subdomains.txt").exists()

    def test_ips(self, tmp_path):
        items = [
            {"_type": "ip", "ip": "10.0.0.1"},
            {"_type": "ip", "ip": "10.0.0.2"},
        ]
        export_typed_outputs(str(tmp_path), items)
        content = (tmp_path / "hosts" / "ips.txt").read_text()
        assert "10.0.0.1" in content
        assert "10.0.0.2" in content

    def test_certificates_as_jsonl(self, tmp_path):
        items = [
            {
                "_type": "certificate",
                "subject": "*.example.com",
                "issuer": "Let's Encrypt",
            },
        ]
        export_typed_outputs(str(tmp_path), items)
        assert (tmp_path / "certs" / "certificates.jsonl").exists()

    def test_domains_to_osint(self, tmp_path):
        items = [{"_type": "domain", "domain": "example.com"}]
        export_typed_outputs(str(tmp_path), items)
        assert (tmp_path / "osint" / "domains.txt").exists()

    def test_user_accounts_as_jsonl(self, tmp_path):
        items = [{"_type": "user_account", "username": "admin", "site": "ssh"}]
        export_typed_outputs(str(tmp_path), items)
        assert (tmp_path / "evidence" / "creds" / "accounts.jsonl").exists()


# ── timestamped snapshots ─────────────────────────────────────────


class TestTimestampedExport:
    def test_only_master_file_created(self, tmp_path):
        """No timestamped snapshots — only master files."""
        items = [{"_type": "subdomain", "host": "a.example.com"}]
        export_typed_outputs(str(tmp_path), items)
        files = list((tmp_path / "subdomains").iterdir())
        assert len(files) == 1
        assert files[0].name == "subdomains.txt"

    def test_only_master_jsonl_created(self, tmp_path):
        items = [{"_type": "user_account", "username": "admin", "site": "ssh"}]
        export_typed_outputs(str(tmp_path), items)
        master = tmp_path / "evidence" / "creds" / "accounts.jsonl"
        assert master.exists()
        # No timestamped file
        files = list((tmp_path / "evidence" / "creds").iterdir())
        assert len(files) == 1

    def test_summary_shows_new_count(self, tmp_path):
        items1 = [{"_type": "subdomain", "host": "a.example.com"}]
        export_typed_outputs(str(tmp_path), items1)

        items2 = [
            {"_type": "subdomain", "host": "a.example.com"},
            {"_type": "subdomain", "host": "b.example.com"},
        ]
        summaries = export_typed_outputs(str(tmp_path), items2)
        assert len(summaries) == 1
        assert "2 items" in summaries[0]
        assert "1 new" in summaries[0]

    def test_summary_all_new(self, tmp_path):
        """When all items are new, summary should not show 'new' count."""
        items = [{"_type": "subdomain", "host": "a.example.com"}]
        summaries = export_typed_outputs(str(tmp_path), items)
        assert "new" not in summaries[0]

    def test_master_file_merges_across_runs(self, tmp_path):
        """Master file should contain all items from all runs."""
        items1 = [{"_type": "ip", "ip": "1.1.1.1"}]
        items2 = [{"_type": "ip", "ip": "2.2.2.2"}]
        export_typed_outputs(str(tmp_path), items1)
        export_typed_outputs(str(tmp_path), items2)

        master = tmp_path / "hosts" / "ips.txt"
        content = master.read_text().strip().splitlines()
        assert "1.1.1.1" in content
        assert "2.2.2.2" in content


# ── collect_typed_outputs ─────────────────────────────────────────


class TestCollectTypedOutputs:
    def _make_step_runner(self, typed_outputs: list) -> MagicMock:
        runner = MagicMock()
        runner.reg_get = AsyncMock(
            return_value={"typed_outputs": typed_outputs, "stdout": ""}
        )
        return runner

    def _make_job_runner(self, step_outputs: list[list]) -> MagicMock:
        from ofx.runner.job import JobRunner

        runner = MagicMock(spec=JobRunner)
        runner._runners = {}
        for i, typed in enumerate(step_outputs):
            runner._runners[str(i)] = self._make_step_runner(typed)
        return runner

    def _make_matrix_runner(self, job_outputs: list[list[list]]) -> MagicMock:
        from ofx.runner.job import JobRunner, MatrixJobRunner

        runner = MagicMock(spec=MatrixJobRunner)
        runner._runners = {}
        for i, step_outputs in enumerate(job_outputs):
            child = MagicMock(spec=JobRunner)
            child._runners = {}
            for j, typed in enumerate(step_outputs):
                child._runners[str(j)] = self._make_step_runner(typed)
            runner._runners[f"job_{i}"] = child
        return runner

    def test_collects_from_job_runners(self):
        runners = {
            "job1": self._make_job_runner(
                [
                    [{"_type": "subdomain", "host": "a.example.com"}],
                    [{"_type": "url", "url": "https://example.com"}],
                ]
            ),
        }
        result = asyncio.run(collect_typed_outputs(runners))
        assert len(result) == 2

    def test_collects_from_matrix_runners(self):
        runners = {
            "matrix_job": self._make_matrix_runner(
                [
                    [[{"_type": "subdomain", "host": "a.com"}]],
                    [[{"_type": "subdomain", "host": "b.com"}]],
                ]
            ),
        }
        result = asyncio.run(collect_typed_outputs(runners))
        assert len(result) == 2

    def test_mixed_job_and_matrix(self):
        runners = {
            "job1": self._make_job_runner(
                [
                    [{"_type": "ip", "ip": "10.0.0.1"}],
                ]
            ),
            "matrix_job": self._make_matrix_runner(
                [
                    [[{"_type": "subdomain", "host": "a.com"}]],
                ]
            ),
        }
        result = asyncio.run(collect_typed_outputs(runners))
        assert len(result) == 2

    def test_empty_runners(self):
        result = asyncio.run(collect_typed_outputs({}))
        assert result == []

    def test_runners_with_no_typed_outputs(self):
        runner = MagicMock()
        runner.reg_get = AsyncMock(return_value={"stdout": "hello"})
        # Make it look like a generic runner (not JobRunner or MatrixJobRunner)
        runners = {"other": runner}
        result = asyncio.run(collect_typed_outputs(runners))
        assert result == []

    def test_handles_step_runner_error(self):
        from ofx.runner.job import JobRunner

        runner = MagicMock(spec=JobRunner)
        failing_step = MagicMock()
        failing_step.reg_get = AsyncMock(side_effect=RuntimeError("boom"))
        runner._runners = {"0": failing_step}

        runners = {"job1": runner}
        result = asyncio.run(collect_typed_outputs(runners))
        assert result == []

    def test_collect_typed_outputs_recurses_to_step_leaves(self):
        leaf_a = MagicMock()
        leaf_a.reg_get = AsyncMock(return_value={"typed_outputs": [{"_type": "ip", "ip": "1.1.1.1"}]})
        leaf_b = MagicMock()
        leaf_b.reg_get = AsyncMock(return_value={"typed_outputs": [{"_type": "ip", "ip": "2.2.2.2"}]})
        child = MagicMock()
        child._runners = {"0": leaf_a, "1": leaf_b}
        root = MagicMock()
        root._runners = {"job": child}

        leaves = asyncio.run(collect_typed_outputs({"root": root}))

        assert leaves == [
            {"_type": "ip", "ip": "1.1.1.1"},
            {"_type": "ip", "ip": "2.2.2.2"},
        ]
