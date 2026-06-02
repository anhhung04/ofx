"""Tests for time window CLI, project status, and project init enhancements."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# A. CLI time-window executor tests
# ---------------------------------------------------------------------------


def _make_runner(*, vars_: dict | None = None, time_guard=None, is_reused=False):
    """Build a minimal mock that quacks like WorkflowRunner."""
    runner = MagicMock()
    runner._time_guard = time_guard
    runner._is_reused = is_reused
    runner.ctx = MagicMock()
    runner.ctx.vars = vars_ or {}
    runner._log_warning = MagicMock()
    runner._log_error = MagicMock()
    runner._log_info = MagicMock()
    return runner


def _call_apply(runner):
    """Invoke the real WorkflowExecutor time-window helper."""
    from ofx.runner.executors.workflow import WorkflowExecutor

    WorkflowExecutor().apply_cli_time_window(runner)


def _call_activate(runner, window, *, denied_message: str, active_message: str | None = None):
    from ofx.runner.executors.workflow import WorkflowExecutor

    WorkflowExecutor()._activate_time_window(
        runner,
        window,
        denied_message=denied_message,
        active_message=active_message,
    )


class TestApplyCliTimeWindow:
    """Tests for WorkflowExecutor.apply_cli_time_window."""

    def test_skipped_when_time_guard_already_set(self):
        existing_guard = MagicMock()
        runner = _make_runner(
            vars_={"_cli_time_window": "09:00-17:00"},
            time_guard=existing_guard,
        )
        _call_apply(runner)
        assert runner._time_guard is existing_guard

    def test_skipped_when_is_reused(self):
        runner = _make_runner(
            vars_={"_cli_time_window": "09:00-17:00"},
            is_reused=True,
        )
        _call_apply(runner)
        assert runner._time_guard is None

    def test_skipped_when_no_cli_time_window_var(self):
        runner = _make_runner(vars_={})
        _call_apply(runner)
        assert runner._time_guard is None

    def test_skipped_when_empty_string(self):
        runner = _make_runner(vars_={"_cli_time_window": ""})
        _call_apply(runner)
        assert runner._time_guard is None

    def test_skipped_when_no_dash(self):
        runner = _make_runner(vars_={"_cli_time_window": "0900"})
        _call_apply(runner)
        assert runner._time_guard is None

    @patch("ofx.profiles.time_window.check_time_window")
    @patch("ofx.profiles.time_window.TimeWindowGuard")
    def test_creates_guard_when_allowed(self, MockGuard, mock_check):
        mock_check.return_value = {
            "allowed": True,
            "remaining_minutes": 120,
            "message": "",
        }
        guard_instance = MagicMock()
        MockGuard.return_value = guard_instance

        runner = _make_runner(vars_={"_cli_time_window": "09:00-17:00"})
        _call_apply(runner)

        mock_check.assert_called_once()
        window_arg = mock_check.call_args[0][0]
        assert window_arg.enabled is True
        assert window_arg.start == "09:00"
        assert window_arg.end == "17:00"
        assert window_arg.abort_on_expire is True

        MockGuard.assert_called_once()
        guard_instance.start.assert_called_once()
        assert runner._time_guard is guard_instance
        runner._log_info.assert_called()

    @patch("ofx.profiles.time_window.check_time_window")
    def test_raises_when_outside_window(self, mock_check):
        mock_check.return_value = {
            "allowed": False,
            "remaining_minutes": 0,
            "message": "Current time 22:00 UTC is outside the allowed window",
        }
        runner = _make_runner(vars_={"_cli_time_window": "09:00-17:00"})
        with pytest.raises(RuntimeError, match="Workflow aborted"):
            _call_apply(runner)
        assert runner._time_guard is None

    @patch("ofx.profiles.time_window.check_time_window")
    @patch("ofx.profiles.time_window.TimeWindowGuard")
    def test_logs_warning_when_message_present(self, MockGuard, mock_check):
        mock_check.return_value = {
            "allowed": True,
            "remaining_minutes": 5,
            "message": "⚠️  Only 5 minutes remaining",
        }
        MockGuard.return_value = MagicMock()

        runner = _make_runner(vars_={"_cli_time_window": "09:00-17:00"})
        _call_apply(runner)

        runner._log_warning.assert_called_with("⚠️  Only 5 minutes remaining")

    @patch("ofx.profiles.time_window.check_time_window")
    @patch("ofx.profiles.time_window.TimeWindowGuard")
    def test_handles_whitespace_in_times(self, MockGuard, mock_check):
        mock_check.return_value = {
            "allowed": True,
            "remaining_minutes": 60,
            "message": "",
        }
        MockGuard.return_value = MagicMock()

        runner = _make_runner(vars_={"_cli_time_window": " 08:30 - 16:30 "})
        _call_apply(runner)

        window_arg = mock_check.call_args[0][0]
        assert window_arg.start == "08:30"
        assert window_arg.end == "16:30"


class TestActivateTimeWindow:
    @patch("ofx.profiles.time_window.check_time_window")
    @patch("ofx.profiles.time_window.TimeWindowGuard")
    def test_starts_guard_and_logs_optional_info(self, MockGuard, mock_check):
        mock_check.return_value = {
            "allowed": True,
            "remaining_minutes": 120,
            "message": "",
        }
        guard_instance = MagicMock()
        MockGuard.return_value = guard_instance

        runner = _make_runner()
        window = MagicMock()

        _call_activate(
            runner,
            window,
            denied_message="denied",
            active_message="active",
        )

        MockGuard.assert_called_once()
        guard_instance.start.assert_called_once()
        runner._log_info.assert_called_once_with("active")

    @patch("ofx.profiles.time_window.check_time_window")
    def test_raises_with_composed_denied_message(self, mock_check):
        mock_check.return_value = {
            "allowed": False,
            "remaining_minutes": 0,
            "message": "outside",
        }
        runner = _make_runner()

        with pytest.raises(RuntimeError, match="outside. denied"):
            _call_activate(runner, MagicMock(), denied_message="denied")


# ---------------------------------------------------------------------------
# B. Execution summary panel with time window
# ---------------------------------------------------------------------------


def _minimal_summary(*, time_window=None):
    """Return a minimal unified summary dict."""
    data = {
        "total_jobs": 2,
        "failed_jobs": 0,
        "total_steps": 4,
        "failed_steps": 0,
        "jobs": [
            {
                "jid": "job1",
                "name": "job1",
                "status": "completed",
                "total_steps": 2,
                "steps": [
                    {"name": "s1", "status": "completed", "duration_ms": 100},
                    {"name": "s2", "status": "completed", "duration_ms": 200},
                ],
                "duration_ms": 300,
                "error": "",
            },
        ],
    }
    if time_window is not None:
        data["time_window"] = time_window
    return data


class TestExecutionSummaryPanel:
    """Tests for execution_summary_panel time-window rendering."""

    def test_panel_renders_without_time_window(self):
        from ofx.commands.ui_helpers import execution_summary_panel

        panel = execution_summary_panel(_minimal_summary())
        assert panel is not None

    def test_panel_renders_active_time_window(self):
        from io import StringIO

        from rich.console import Console

        from ofx.commands.ui_helpers import execution_summary_panel
        from ofx.settings import RICH_THEME

        tw = {
            "start": "09:00",
            "end": "17:00",
            "remaining_minutes": 45,
            "aborted": False,
        }
        panel = execution_summary_panel(_minimal_summary(time_window=tw))

        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=120, theme=RICH_THEME)
        console.print(panel)
        output = buf.getvalue()

        assert "09:00" in output
        assert "17:00" in output
        assert "45 min remaining" in output

    def test_panel_renders_expired_time_window(self):
        from io import StringIO

        from rich.console import Console

        from ofx.commands.ui_helpers import execution_summary_panel
        from ofx.settings import RICH_THEME

        tw = {
            "start": "09:00",
            "end": "17:00",
            "remaining_minutes": 0,
            "aborted": True,
        }
        panel = execution_summary_panel(_minimal_summary(time_window=tw))

        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=120, theme=RICH_THEME)
        console.print(panel)
        output = buf.getvalue()

        assert "09:00" in output
        assert "17:00" in output
        assert "EXPIRED" in output
        assert "aborted" in output


# ---------------------------------------------------------------------------
# C. Project init — ENGAGEMENT_FILE_STRUCTURE
# ---------------------------------------------------------------------------


class TestEngagementFileStructure:
    """Test that ENGAGEMENT_FILE_STRUCTURE includes notes and reports."""

    def test_contains_notes(self):
        from ofx.commands.project.handlers.init import ENGAGEMENT_FILE_STRUCTURE

        flat = [e if isinstance(e, str) else e[0] for e in ENGAGEMENT_FILE_STRUCTURE]
        assert "notes" in flat

    def test_contains_reports(self):
        from ofx.commands.project.handlers.init import ENGAGEMENT_FILE_STRUCTURE

        flat = [e if isinstance(e, str) else e[0] for e in ENGAGEMENT_FILE_STRUCTURE]
        assert "reports" in flat

    def test_structure_is_list(self):
        from ofx.commands.project.handlers.init import ENGAGEMENT_FILE_STRUCTURE

        assert isinstance(ENGAGEMENT_FILE_STRUCTURE, list)
        assert len(ENGAGEMENT_FILE_STRUCTURE) > 0


# ---------------------------------------------------------------------------
# D. FlowRunHandler time window injection
# ---------------------------------------------------------------------------


class TestFlowRunHandlerTimeWindow:
    """Test that FlowRunHandler injects _cli_time_window into run_vars."""

    def test_time_window_stored_on_handler(self):
        from ofx.commands.flow.run import FlowRunHandler

        handler = FlowRunHandler(
            workflow_name="test.yml",
            time_window="09:00-17:00",
        )
        assert handler.time_window == "09:00-17:00"

    def test_time_window_empty_by_default(self):
        from ofx.commands.flow.run import FlowRunHandler

        handler = FlowRunHandler(workflow_name="test.yml")
        assert handler.time_window == ""

    def test_cli_time_window_injected_into_run_vars(self):
        with (
            patch(
                "ofx.commands.flow.run.run_workflow", new_callable=AsyncMock
            ) as mock_run_workflow,
            patch("ofx.commands.flow.run.get_workflow_search_dirs", return_value=[]),
        ):
            from ofx.commands.flow.run import FlowRunHandler as FRH

            mock_run_workflow.return_value = MagicMock(
                status=MagicMock(value="completed"),
            )

            handler = FRH(
                workflow_name="test.yml",
                time_window="08:00-12:00",
            )
            handler._configure_logging = MagicMock()
            handler._acquire_lock = MagicMock(return_value=None)
            handler._process_inputs = MagicMock()
            handler._print_summary = MagicMock()
            handler._save_history = MagicMock()
            handler.input = {}
            handler.quiet = True

            asyncio.run(handler.run())

            mock_run_workflow.assert_called_once()
            call_kwargs = mock_run_workflow.call_args
            passed_vars = call_kwargs.kwargs.get("vars") or call_kwargs[1].get("vars")
            assert passed_vars is not None
            assert passed_vars["_cli_time_window"] == "08:00-12:00"

    def test_no_cli_time_window_when_not_set(self):
        with (
            patch(
                "ofx.commands.flow.run.run_workflow", new_callable=AsyncMock
            ) as mock_run_workflow,
            patch("ofx.commands.flow.run.get_workflow_search_dirs", return_value=[]),
        ):
            from ofx.commands.flow.run import FlowRunHandler as FRH

            mock_run_workflow.return_value = MagicMock(
                status=MagicMock(value="completed"),
            )

            handler = FRH(workflow_name="test.yml")
            handler._configure_logging = MagicMock()
            handler._acquire_lock = MagicMock(return_value=None)
            handler._process_inputs = MagicMock()
            handler._print_summary = MagicMock()
            handler._save_history = MagicMock()
            handler.input = {}
            handler.quiet = True

            asyncio.run(handler.run())

            mock_run_workflow.assert_called_once()
            call_kwargs = mock_run_workflow.call_args
            passed_vars = call_kwargs.kwargs.get("vars") or call_kwargs[1].get("vars")
            if passed_vars:
                assert "_cli_time_window" not in passed_vars

    def test_cli_profile_injected_into_run_vars(self):
        with (
            patch(
                "ofx.commands.flow.run.run_workflow", new_callable=AsyncMock
            ) as mock_run_workflow,
            patch("ofx.commands.flow.run.get_workflow_search_dirs", return_value=[]),
        ):
            from ofx.commands.flow.run import FlowRunHandler as FRH

            mock_run_workflow.return_value = MagicMock(
                status=MagicMock(value="completed"),
            )

            handler = FRH(
                workflow_name="test.yml",
                profile_name="stealth",
            )
            handler._configure_logging = MagicMock()
            handler._acquire_lock = MagicMock(return_value=None)
            handler._process_inputs = MagicMock()
            handler._print_summary = MagicMock()
            handler._save_history = MagicMock()
            handler.input = {}
            handler.quiet = True

            asyncio.run(handler.run())

            call_kwargs = mock_run_workflow.call_args
            passed_vars = call_kwargs.kwargs.get("vars") or call_kwargs[1].get("vars")
            assert passed_vars["_cli_profile_name"] == "stealth"
