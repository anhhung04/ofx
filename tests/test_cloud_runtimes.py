"""Tests for cloud runtime helpers: script_runtime and task_runtime."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ofx.cloud.script_runtime import (
    build_python_payload,
    is_python_step_run_type,
    resolve_python_step_source,
)
from ofx.cloud.task_runtime import build_task_command_from_step
from ofx.models.step import RunType, Step
from ofx.runner.task_step import extract_output_item_target, extract_task_target_and_opts

class TestResolvePythonStepSource:
    """Tests for script source resolution."""

    def test_inline_script(self):
        step = Step(script="print('hello')")
        result = resolve_python_step_source(step)
        assert result == "print('hello')"

    def test_inline_script_whitespace(self):
        step = Step(script="  \n  ")
        result = resolve_python_step_source(step)
        assert result == "  \n  "

    def test_script_file_absolute(self, tmp_path):
        script = tmp_path / "run.py"
        script.write_text("x = 1\n")
        step = Step(script_file=str(script.with_suffix("")))
        result = resolve_python_step_source(step)
        assert result == "x = 1\n"

    def test_script_file_relative(self, tmp_path):
        script = tmp_path / "myscript.py"
        script.write_text("y = 2\n")
        step = Step(script_file="myscript")
        result = resolve_python_step_source(step, workflow_dir=tmp_path)
        assert result == "y = 2\n"

    def test_script_file_not_found(self, tmp_path):
        step = Step(script_file="nonexistent")
        with pytest.raises(FileNotFoundError, match="not found"):
            resolve_python_step_source(step, workflow_dir=tmp_path)

    def test_script_file_defaults_to_cwd(self, tmp_path, monkeypatch):
        script = tmp_path / "cwd_script.py"
        script.write_text("z = 3\n")
        monkeypatch.chdir(tmp_path)
        step = Step(script_file="cwd_script")
        result = resolve_python_step_source(step)
        assert result == "z = 3\n"

    def test_unsupported_run_type(self):
        step = Step(run="echo hello")
        with pytest.raises(ValueError, match="Unsupported step run type"):
            resolve_python_step_source(step)

class TestIsPythonStepRunType:
    @pytest.mark.parametrize(
        ("run_type", "expected"),
        [
            (RunType.SCRIPT, True),
            (RunType.SCRIPT_FILE, True),
            (RunType.COMMAND, False),
            (RunType.TASK, False),
        ],
    )
    def test_recognizes_python_backed_step_types(self, run_type, expected):
        assert is_python_step_run_type(run_type) is expected

class TestBuildPythonPayload:
    """Tests for payload building with caching."""

    def test_basic_payload(self):
        result = build_python_payload("print(1)")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_caching(self):
        """Same input should return same cached object."""
        r1 = build_python_payload("print(2)")
        r2 = build_python_payload("print(2)")
        assert r1 is r2

    def test_opsec_mode(self):
        _normal = build_python_payload("print(3)", opsec_mode=False)
        opsec = build_python_payload("print(3)", opsec_mode=True)
        assert isinstance(opsec, str)
        assert len(opsec) > 0

class TestBuildTaskCommandFromStep:
    """Tests for task command building."""

    def test_missing_task_raises(self):
        step = Step(run="echo hi")
        with pytest.raises(RuntimeError, match="missing task name"):
            build_task_command_from_step(step)

    def test_unregistered_task_raises(self):
        step = Step(task="nonexistent_task_xyz", run_with={"target": "10.0.0.1"})
        with pytest.raises(RuntimeError, match="not registered"):
            build_task_command_from_step(step)

    def test_builds_command_from_registered_task(self):
        mock_task_cls = MagicMock()
        mock_task = MagicMock()
        mock_task.output_flag = "-oX"
        mock_task.build_command.return_value = ("nmap -sV 10.0.0.1", [])
        mock_task_cls.return_value = mock_task

        step = Step(task="nmap", run_with={"target": "10.0.0.1", "ports": "80,443"})

        with patch("ofx.tasks.registry.TaskRegistry") as mock_reg:
            mock_reg.get.return_value = mock_task_cls
            result = build_task_command_from_step(step)

        assert result == "nmap -sV 10.0.0.1"
        assert mock_task.output_flag == "-oX"

    def test_output_flag_restored_on_error(self):
        """output_flag must be restored even when build_command fails."""
        mock_task_cls = MagicMock()
        mock_task = MagicMock()
        mock_task.output_flag = "-o"
        mock_task.build_command.side_effect = RuntimeError("bad opts")
        mock_task_cls.return_value = mock_task

        step = Step(task="broken", run_with={"target": "x"})

        with patch("ofx.tasks.registry.TaskRegistry") as mock_reg:
            mock_reg.get.return_value = mock_task_cls
            with pytest.raises(RuntimeError, match="bad opts"):
                build_task_command_from_step(step)

        assert mock_task.output_flag == "-o"

    def test_target_extracted_from_run_with(self):
        mock_task_cls = MagicMock()
        mock_task = MagicMock()
        mock_task.output_flag = None
        mock_task.build_command.return_value = ("tool target.com", [])
        mock_task_cls.return_value = mock_task

        step = Step(task="tool", run_with={"target": "target.com", "verbose": True})

        with patch("ofx.tasks.registry.TaskRegistry") as mock_reg:
            mock_reg.get.return_value = mock_task_cls
            build_task_command_from_step(step)

        call_args = mock_task.build_command.call_args
        assert call_args[0][0] == "target.com"
        assert "target" not in call_args[1]
        assert call_args[1]["verbose"] is True

    def test_target_list_is_joined_consistently(self):
        mock_task_cls = MagicMock()
        mock_task = MagicMock()
        mock_task.output_flag = None
        mock_task.build_command.return_value = ("tool a,b", [])
        mock_task_cls.return_value = mock_task

        step = Step(task="tool", run_with={"targets": ["a", "b"], "verbose": True})

        with patch("ofx.tasks.registry.TaskRegistry") as mock_reg:
            mock_reg.get.return_value = mock_task_cls
            build_task_command_from_step(step)

        call_args = mock_task.build_command.call_args
        assert call_args[0][0] == "a,b"
        assert "target" not in call_args[1]
        assert "targets" not in call_args[1]
        assert call_args[1]["verbose"] is True

    def test_profile_options_are_merged_before_build(self):
        mock_task_cls = MagicMock()
        mock_task = MagicMock()
        mock_task.output_flag = None
        mock_task.opts = {"threads": None, "proxy": None}
        mock_task.build_command.return_value = ("tool target", [])
        mock_task_cls.return_value = mock_task
        profile = object()
        step = Step(task="tool", run_with={"target": "target", "threads": 5})

        with (
            patch("ofx.tasks.registry.TaskRegistry") as mock_reg,
            patch("ofx.cloud.task_runtime.merge_profile_task_options") as mock_merge,
        ):
            mock_reg.get.return_value = mock_task_cls
            mock_merge.return_value = ({"threads": 5, "proxy": "socks5://127.0.0.1:9050"}, [], ["proxy"])

            build_task_command_from_step(step, profile=profile)

        mock_merge.assert_called_once_with(
            task_name="tool",
            user_opts={"threads": 5},
            task_declared_opts=mock_task.opts,
            profile=profile,
        )
        mock_task.build_command.assert_called_once_with(
            "target",
            threads=5,
            proxy="socks5://127.0.0.1:9050",
        )

    def test_profile_command_adaptation_runs_after_build(self):
        mock_task_cls = MagicMock()
        mock_task = MagicMock()
        mock_task.output_flag = None
        mock_task.opts = {}
        mock_task.build_command.return_value = ("whois example.com", [])
        mock_task_cls.return_value = mock_task
        profile = object()
        step = Step(task="whois", run_with={"target": "example.com"})

        with (
            patch("ofx.tasks.registry.TaskRegistry") as mock_reg,
            patch("ofx.cloud.task_runtime.adapt_task_command_for_profile") as mock_adapt,
        ):
            mock_reg.get.return_value = mock_task_cls
            mock_adapt.return_value = "env HTTP_PROXY=socks5://127.0.0.1:9050 whois example.com"

            result = build_task_command_from_step(step, profile=profile)

        mock_adapt.assert_called_once_with(
            "whois example.com",
            task_declared_opts=mock_task.opts,
            resolved_opts={},
            profile=profile,
        )
        assert result == "env HTTP_PROXY=socks5://127.0.0.1:9050 whois example.com"

class TestTaskStepHelpers:
    def test_extract_task_target_and_opts_normalizes_lists_and_scalars(self):
        assert extract_task_target_and_opts({"targets": ["a", "b"]}) == ("a,b", {})
        assert extract_task_target_and_opts({"target": "example.com"}) == ("example.com", {})
        assert extract_task_target_and_opts({"target": 10, "verbose": True}) == ("10", {"verbose": True})

    def test_extract_output_item_target_prefers_domain_host_ip_then_url(self):
        assert extract_output_item_target({"domain": "example.com", "host": "api.example.com"}) == "example.com"
        assert extract_output_item_target({"host": "api.example.com"}) == "api.example.com"
        assert extract_output_item_target({"ip": "10.0.0.1"}) == "10.0.0.1"
        assert extract_output_item_target({"url": "https://example.com:8443/path"}) == "example.com"
        assert extract_output_item_target({}) == ""
