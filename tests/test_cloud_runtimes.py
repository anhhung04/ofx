"""Tests for cloud runtime helpers: script_runtime and task_runtime."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ofx.cloud.script_runtime import (
    build_python_payload,
    resolve_python_step_source,
)
from ofx.cloud.task_runtime import build_task_command_from_step
from ofx.models.step import Step

# =========================================================================
# resolve_python_step_source
# =========================================================================


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
        step = Step(script_file=str(script.with_suffix("")))  # without .py
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


# =========================================================================
# build_python_payload
# =========================================================================


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
        assert r1 is r2  # exact same object from lru_cache

    def test_opsec_mode(self):
        _normal = build_python_payload("print(3)", opsec_mode=False)
        opsec = build_python_payload("print(3)", opsec_mode=True)
        # Both produce strings; opsec should differ (obfuscated)
        assert isinstance(opsec, str)
        assert len(opsec) > 0


# =========================================================================
# build_task_command_from_step
# =========================================================================


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
        # output_flag should be restored after build
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
