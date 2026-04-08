"""Tests for ``ofx flow tasks run`` CLI command and TaskRunHandler."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── parse_opt_args ────────────────────────────────────────────────────────


class TestParseOptArgs:
    """Verify CLI --opt parsing into a dict."""

    def test_key_value_string(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["key=value"])
        assert result == {"key": "value"}

    def test_key_value_int(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["ports=1000"])
        assert result == {"ports": 1000}

    def test_key_value_float(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["delay=2.5"])
        assert result == {"delay": 2.5}

    def test_key_value_bool_true(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["verbose=true"])
        assert result == {"verbose": True}

    def test_key_value_bool_false(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["verbose=false"])
        assert result == {"verbose": False}

    def test_bare_key_is_true(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["verbose"])
        assert result == {"verbose": True}

    def test_multiple_opts(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["threads=50", "verbose", "target=10.0.0.1"])
        assert result == {"threads": 50, "verbose": True, "target": "10.0.0.1"}

    def test_empty_list(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args([])
        assert result == {}

    def test_string_with_equals_in_value(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["header=X-Auth=secret123"])
        assert result == {"header": "X-Auth=secret123"}

    def test_whitespace_handling(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["  key = value  "])
        assert result == {"key": "value"}


# ── _pick_columns ─────────────────────────────────────────────────────────


class TestPickColumns:
    """Verify column selection for output type display."""

    def test_port_type_columns(self):
        from ofx.commands.flow.run_task import _pick_columns

        items = [{"ip": "10.0.0.1", "port": 80, "protocol": "tcp"}]
        cols = _pick_columns("port", items)
        assert "ip" in cols
        assert "port" in cols

    def test_url_type_columns(self):
        from ofx.commands.flow.run_task import _pick_columns

        items = [{"url": "https://example.com", "status_code": 200, "title": "Example"}]
        cols = _pick_columns("url", items)
        assert "url" in cols
        assert "status_code" in cols

    def test_unknown_type_uses_item_keys(self):
        from ofx.commands.flow.run_task import _pick_columns

        items = [{"foo": "bar", "baz": 42, "_internal": "skip"}]
        cols = _pick_columns("custom", items)
        assert "foo" in cols
        assert "baz" in cols
        assert "_internal" not in cols

    def test_empty_items(self):
        from ofx.commands.flow.run_task import _pick_columns

        cols = _pick_columns("port", [])
        assert cols == []

    def test_skips_columns_without_data(self):
        from ofx.commands.flow.run_task import _pick_columns

        items = [{"ip": "10.0.0.1", "port": 80}]  # no protocol, service_name, host
        cols = _pick_columns("port", items)
        assert "ip" in cols
        assert "port" in cols
        # Columns with no data should be excluded
        assert "service_name" not in cols


# ── TaskRunHandler ────────────────────────────────────────────────────────


class TestTaskRunHandler:
    """Test the task run handler logic."""

    def test_unknown_task_returns_error(self):
        from ofx.commands.flow.run_task import TaskRunHandler

        handler = TaskRunHandler(
            task_name="nonexistent_tool_xyz",
            target="example.com",
            opts={},
        )
        result = asyncio.run(handler.run())
        assert result == 1

    def test_handler_creates_with_defaults(self):
        from ofx.commands.flow.run_task import TaskRunHandler

        handler = TaskRunHandler(
            task_name="nmap",
            target="10.0.0.1",
            opts={"ports": "80,443"},
        )
        assert handler.task_name == "nmap"
        assert handler.target == "10.0.0.1"
        assert handler.opts == {"ports": "80,443"}
        assert handler.timeout == 60
        assert handler.store_creds is False
        assert handler.json_output is False

    def test_handler_with_all_options(self):
        from ofx.commands.flow.run_task import TaskRunHandler

        handler = TaskRunHandler(
            task_name="httpx",
            target="targets.txt",
            opts={"threads": 50},
            profile="stealth",
            timeout=30,
            output="/tmp/results",
            store_creds=True,
            json_output=True,
        )
        assert handler.profile_name == "stealth"
        assert handler.timeout == 30
        assert handler.output == "/tmp/results"
        assert handler.store_creds is True
        assert handler.json_output is True


# ── Profile Common Opt Injection ──────────────────────────────────────────


class TestProfileCommonOptInjection:
    """Verify that profile-level settings auto-map to task opts."""

    def _make_runner(self, profile, task_name="httpx", user_opts=None):
        from ofx.runner.core.models import RunContext
        from ofx.runner.tasks.runner import TaskExecution, TaskRunner

        ctx = RunContext(vars={"profile": profile})
        model = TaskExecution(
            task_name=task_name,
            target="example.com",
            opts=user_opts or {},
        )
        runner = TaskRunner(model, ctx)
        # Pre-initialize the task so common mapping can inspect opts
        from ofx.tasks import TaskRegistry

        task_cls = TaskRegistry.get(task_name)
        if task_cls:
            runner._task = task_cls()
        return runner

    def test_proxy_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(proxy="socks5://127.0.0.1:9050")
        runner = self._make_runner(profile, task_name="feroxbuster")
        runner._apply_profile_task_options()
        assert runner.model.opts.get("proxy") == "socks5://127.0.0.1:9050"

    def test_threads_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(threads=5)
        runner = self._make_runner(profile)
        runner._apply_profile_task_options()
        assert runner.model.opts.get("threads") == 5

    def test_rate_limit_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(rate_limit=30)
        runner = self._make_runner(profile)
        runner._apply_profile_task_options()
        assert runner.model.opts.get("rate_limit") == 30

    def test_delay_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(delay=2.0)
        runner = self._make_runner(profile, task_name="katana")
        runner._apply_profile_task_options()
        assert runner.model.opts.get("delay") == 2.0

    def test_user_opts_win_over_profile(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(threads=5, rate_limit=30)
        runner = self._make_runner(profile, user_opts={"threads": 100})
        runner._apply_profile_task_options()
        # User's threads=100 should win
        assert runner.model.opts["threads"] == 100
        # Profile's rate_limit should still be injected
        assert runner.model.opts.get("rate_limit") == 30

    def test_zero_values_not_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(threads=0, rate_limit=0)
        runner = self._make_runner(profile)
        runner._apply_profile_task_options()
        assert "threads" not in runner.model.opts
        assert "rate_limit" not in runner.model.opts

    def test_empty_string_not_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(proxy="")
        runner = self._make_runner(profile)
        runner._apply_profile_task_options()
        assert "proxy" not in runner.model.opts

    def test_task_without_matching_opt_skipped(self):
        """Profile proxy is not injected into tasks that don't declare a proxy opt."""
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(proxy="socks5://127.0.0.1:9050")
        runner = self._make_runner(profile, task_name="whois")
        runner._apply_profile_task_options()
        assert "proxy" not in runner.model.opts

    def test_combined_profile_and_task_options(self):
        """Profile common fields + per-task overrides merge correctly."""
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(
            threads=5,
            proxy="socks5://127.0.0.1:9050",
            task_options={"feroxbuster": {"insecure": True}},
        )
        runner = self._make_runner(profile, task_name="feroxbuster")
        runner._apply_profile_task_options()
        # Common field injection
        assert runner.model.opts.get("threads") == 5
        assert runner.model.opts.get("proxy") == "socks5://127.0.0.1:9050"
        # Per-task override
        assert runner.model.opts.get("insecure") is True
