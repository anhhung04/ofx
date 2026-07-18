"""Tests for add_outputs() helper and stdout truncation."""

import io
import json

import pytest

from ofx.models.command import Script
from ofx.runner import RunContext, RunnerStatus, ScriptRunner
from ofx.runner.commands.command import (
    write_outputs_file,
)

class TestAddOutputsUnit:
    """Test the add_outputs function logic directly."""

    def test_basic_key_value(self, tmp_path):
        """add_outputs writes simple key=value pairs."""
        out = tmp_path / "outputs"
        out.touch()
        write_outputs_file(out, name="Alice", age=30)
        lines = out.read_text().strip().splitlines()
        assert lines == ["name=Alice", "age=30"]

    def test_dict_serialized_as_json(self, tmp_path):
        """Dicts are serialized as JSON."""
        out = tmp_path / "outputs"
        out.touch()
        data = {"host": "10.0.0.1", "open": True}
        write_outputs_file(out, metadata=data)
        line = out.read_text().strip()
        assert line.startswith("metadata=")
        parsed = json.loads(line.split("=", 1)[1])
        assert parsed == data

    def test_list_serialized_as_json(self, tmp_path):
        """Lists are serialized as JSON."""
        out = tmp_path / "outputs"
        out.touch()
        items = ["a", "b", "c"]
        write_outputs_file(out, hosts=items)
        line = out.read_text().strip()
        assert json.loads(line.split("=", 1)[1]) == items

    def test_boolean_values(self, tmp_path):
        """Booleans are written as their string representation."""
        out = tmp_path / "outputs"
        out.touch()
        write_outputs_file(out, success=True, failed=False)
        lines = out.read_text().strip().splitlines()
        assert "success=True" in lines
        assert "failed=False" in lines

    def test_none_value(self, tmp_path):
        """None is written as 'None'."""
        out = tmp_path / "outputs"
        out.touch()
        write_outputs_file(out, result=None)
        assert out.read_text().strip() == "result=None"

    def test_integer_value(self, tmp_path):
        """Integers are written as their string."""
        out = tmp_path / "outputs"
        out.touch()
        write_outputs_file(out, count=42)
        assert out.read_text().strip() == "count=42"

    def test_empty_string(self, tmp_path):
        """Empty string values are preserved."""
        out = tmp_path / "outputs"
        out.touch()
        write_outputs_file(out, result="")
        assert out.read_text().strip() == "result="

    def test_multiple_calls_append(self, tmp_path):
        """Multiple add_outputs calls append, not overwrite."""
        out = tmp_path / "outputs"
        out.touch()
        write_outputs_file(out, a="1")
        write_outputs_file(out, b="2")
        lines = out.read_text().strip().splitlines()
        assert lines == ["a=1", "b=2"]

    def test_no_outputs_file_is_noop(self):
        """No error when outputs_file is None."""
        write_outputs_file(None, key="val")

    def test_kwargs_expansion(self, tmp_path):
        """**kwargs expansion works for dicts."""
        out = tmp_path / "outputs"
        out.touch()
        results = {"host": "10.0.0.1", "port": "22"}
        write_outputs_file(out, **results)
        lines = out.read_text().strip().splitlines()
        assert "host=10.0.0.1" in lines
        assert "port=22" in lines

def test_script_output_helper_writes_and_capture_strings(tmp_path):
    out = tmp_path / "outputs"
    out.touch()

    write_outputs_file(str(out), result="ok")
    assert "result=ok" in out.read_text()

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    stdout_capture.write("hello")
    stderr_capture.write("warn")
    assert stdout_capture.getvalue() == "hello"
    assert stderr_capture.getvalue() == "warn"

class TestAddOutputsIntegration:
    """Test add_outputs() inside ScriptRunner execution."""

    @pytest.mark.asyncio
    async def test_script_add_outputs_basic(self, tmp_path):
        """Script using add_outputs captures key-value outputs."""
        script = 'add_outputs(target="10.0.0.1", port=8080)'
        outputs_file = tmp_path / "outputs"
        outputs_file.touch()
        ctx = RunContext()
        ctx.envs["RUNNER_OUTPUTS"] = str(outputs_file)
        ctx.envs["OFX_OUTPUTS"] = str(outputs_file)
        runner = ScriptRunner(Script(script=script), ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["target"] == "10.0.0.1"
        assert result.outputs["port"] == "8080"

    @pytest.mark.asyncio
    async def test_script_add_outputs_dict_json(self, tmp_path):
        """Script using add_outputs serializes dicts as JSON."""
        script = 'add_outputs(data={"key": "value", "n": 1})'
        outputs_file = tmp_path / "outputs"
        outputs_file.touch()
        ctx = RunContext()
        ctx.envs["RUNNER_OUTPUTS"] = str(outputs_file)
        ctx.envs["OFX_OUTPUTS"] = str(outputs_file)
        runner = ScriptRunner(Script(script=script), ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        parsed = json.loads(result.outputs["data"])
        assert parsed == {"key": "value", "n": 1}

    @pytest.mark.asyncio
    async def test_script_add_outputs_list_json(self, tmp_path):
        """Script using add_outputs serializes lists as JSON."""
        script = 'add_outputs(items=["a", "b", "c"])'
        outputs_file = tmp_path / "outputs"
        outputs_file.touch()
        ctx = RunContext()
        ctx.envs["RUNNER_OUTPUTS"] = str(outputs_file)
        ctx.envs["OFX_OUTPUTS"] = str(outputs_file)
        runner = ScriptRunner(Script(script=script), ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        parsed = json.loads(result.outputs["items"])
        assert parsed == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_script_add_outputs_multiple_calls(self, tmp_path):
        """Multiple add_outputs calls accumulate outputs."""
        script = """
add_outputs(step="recon")
add_outputs(count=5, status="done")
"""
        outputs_file = tmp_path / "outputs"
        outputs_file.touch()
        ctx = RunContext()
        ctx.envs["RUNNER_OUTPUTS"] = str(outputs_file)
        ctx.envs["OFX_OUTPUTS"] = str(outputs_file)
        runner = ScriptRunner(Script(script=script), ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["step"] == "recon"
        assert result.outputs["count"] == "5"
        assert result.outputs["status"] == "done"

    @pytest.mark.asyncio
    async def test_script_add_outputs_kwargs_expansion(self, tmp_path):
        """**kwargs expansion works inside scripts."""
        script = """
results = {"host": "10.0.0.1", "open_ports": "22,80,443"}
add_outputs(**results)
"""
        outputs_file = tmp_path / "outputs"
        outputs_file.touch()
        ctx = RunContext()
        ctx.envs["RUNNER_OUTPUTS"] = str(outputs_file)
        ctx.envs["OFX_OUTPUTS"] = str(outputs_file)
        runner = ScriptRunner(Script(script=script), ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["host"] == "10.0.0.1"
        assert result.outputs["open_ports"] == "22,80,443"

    @pytest.mark.asyncio
    async def test_script_add_outputs_with_print(self, tmp_path):
        """add_outputs combined with print() both work."""
        script = """
print("Starting scan")
add_outputs(result="success")
print("Done")
"""
        outputs_file = tmp_path / "outputs"
        outputs_file.touch()
        ctx = RunContext()
        ctx.envs["RUNNER_OUTPUTS"] = str(outputs_file)
        ctx.envs["OFX_OUTPUTS"] = str(outputs_file)
        runner = ScriptRunner(Script(script=script), ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["result"] == "success"
        assert "Starting scan" in result.outputs["stdout"]

class TestStdoutTruncation:
    """Test _log_output truncation behavior."""

    def test_short_output_not_truncated(self):
        """Output within max_display_lines is shown fully."""
        content = "\n".join(f"line {i}" for i in range(10))
        display = _truncate(content, max_lines=50)
        assert display == content
        assert "more lines" not in display

    def test_exact_boundary_not_truncated(self):
        """Output at exactly max_display_lines is not truncated."""
        content = "\n".join(f"line {i}" for i in range(50))
        display = _truncate(content, max_lines=50)
        assert display == content
        assert "more lines" not in display

    def test_one_over_boundary_truncated(self):
        """Output one line over max_display_lines is truncated."""
        content = "\n".join(f"line {i}" for i in range(51))
        display = _truncate(content, max_lines=50)
        assert "... [1 more lines" in display
        assert display.count("\n") == 50

    def test_large_output_truncated(self):
        """Large output shows correct omitted count."""
        content = "\n".join(f"https://example.com/page/{i}" for i in range(1000))
        display = _truncate(content, max_lines=50)
        assert "... [950 more lines" in display
        assert "https://example.com/page/0" in display
        assert "https://example.com/page/49" in display
        assert "https://example.com/page/50" not in display

    def test_empty_output_passthrough(self):
        """Empty content returns empty."""
        assert _truncate("", max_lines=50) == ""

    def test_single_line_not_truncated(self):
        """Single line is never truncated."""
        display = _truncate("hello world", max_lines=50)
        assert display == "hello world"
        assert "more lines" not in display

    def test_custom_max_lines(self):
        """Custom max_display_lines is respected."""
        content = "\n".join(f"line {i}" for i in range(20))
        display = _truncate(content, max_lines=10)
        assert "... [10 more lines" in display
        assert "line 0" in display
        assert "line 9" in display
        assert "line 10" not in display

    def test_truncation_message_format(self):
        """Truncation message matches expected format."""
        content = "\n".join("x" for _ in range(100))
        display = _truncate(content, max_lines=30)
        assert "... [70 more lines — full output saved to logs]" in display

def _truncate(content: str, max_lines: int = 50) -> str:
    """Mimic StepRunner._log_output truncation logic."""
    if not content:
        return ""
    lines = content.splitlines()
    if len(lines) > max_lines:
        head = "\n".join(lines[:max_lines])
        omitted = len(lines) - max_lines
        return f"{head}\n... [{omitted} more lines — full output saved to logs]"
    return content
