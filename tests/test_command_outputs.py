"""Tests for OFX_OUTPUTS feature in command runner"""

from pathlib import Path

import pytest

from ofx.models.command import Command
from ofx.runner import CommandRunner, RunContext, RunnerStatus


class TestCommandOutputs:
    """Test OFX_OUTPUTS environment variable capture"""

    @pytest.mark.asyncio
    async def test_capture_single_output(self):
        """Test capturing a single key-value output"""
        cmd = 'echo "test_key=test_value" >> $OFX_OUTPUTS'
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert "test_key" in result.outputs
        assert result.outputs["test_key"] == "test_value"

    @pytest.mark.asyncio
    async def test_capture_multiple_outputs(self):
        """Test capturing multiple key-value outputs"""
        cmd = """
echo "name=Alice" >> $OFX_OUTPUTS
echo "age=30" >> $OFX_OUTPUTS
echo "city=Paris" >> $OFX_OUTPUTS
"""
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["name"] == "Alice"
        assert result.outputs["age"] == "30"
        assert result.outputs["city"] == "Paris"

    @pytest.mark.asyncio
    async def test_output_with_spaces(self):
        """Test capturing output values with spaces"""
        cmd = 'echo "message=Hello World" >> $OFX_OUTPUTS'
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["message"] == "Hello World"

    @pytest.mark.asyncio
    async def test_output_with_special_chars(self):
        """Test capturing output values with special characters"""
        cmd = 'echo "url=https://example.com/path?key=value&foo=bar" >> $OFX_OUTPUTS'
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["url"] == "https://example.com/path?key=value&foo=bar"

    @pytest.mark.asyncio
    async def test_outputs_file_cleaned_up(self):
        """Test that the outputs file is cleaned up after execution"""
        cmd = 'echo "cleanup_test=success" >> $OFX_OUTPUTS'
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        outputs_file_path = None

        await runner._pre_run()
        await runner._do_run()

        if runner._outputs_file:
            outputs_file_path = runner._outputs_file

        await runner._post_run()

        if outputs_file_path:
            assert not outputs_file_path.exists()

    @pytest.mark.asyncio
    async def test_empty_outputs_file(self):
        """Test handling of empty outputs file"""
        cmd = 'echo "test" > /dev/null'
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert "stdout" in result.outputs
        assert "stderr" in result.outputs

    @pytest.mark.asyncio
    async def test_malformed_output_line_ignored(self):
        """Test that malformed lines are ignored"""
        cmd = """
echo "valid_key=valid_value" >> $OFX_OUTPUTS
echo "malformed line without equals" >> $OFX_OUTPUTS
echo "another_key=another_value" >> $OFX_OUTPUTS
"""
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["valid_key"] == "valid_value"
        assert result.outputs["another_key"] == "another_value"

    @pytest.mark.asyncio
    async def test_outputs_overwrite_previous(self):
        """Test that multiple assignments overwrite previous values"""
        cmd = """
echo "counter=1" >> $OFX_OUTPUTS
echo "counter=2" >> $OFX_OUTPUTS
echo "counter=3" >> $OFX_OUTPUTS
"""
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["counter"] == "3"

    @pytest.mark.asyncio
    async def test_output_with_equals_in_value(self):
        """Test capturing values that contain equals signs"""
        cmd = 'echo "equation=a=b+c" >> $OFX_OUTPUTS'
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["equation"] == "a=b+c"

    @pytest.mark.asyncio
    async def test_multiline_output_value(self):
        """Test that multiline values work with proper quoting"""
        cmd = """cat << 'EOF' >> $OFX_OUTPUTS
json={"key": "value", "array": [1, 2, 3]}
EOF
"""
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert "json" in result.outputs
        assert '{"key": "value"' in result.outputs["json"]

    @pytest.mark.asyncio
    async def test_no_outputs_file_in_interactive_mode(self):
        """Test that OFX_OUTPUTS is not created in interactive mode"""
        cmd = 'echo "should_not_capture=value"'
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd, interactive=True), ctx)

        await runner._pre_run()
        assert runner._outputs_file is None
        assert "OFX_OUTPUTS" not in runner.ctx.envs

    @pytest.mark.asyncio
    async def test_numeric_values_as_strings(self):
        """Test that numeric values are captured as strings"""
        cmd = """
echo "port=8080" >> $OFX_OUTPUTS
echo "count=42" >> $OFX_OUTPUTS
echo "ratio=3.14" >> $OFX_OUTPUTS
"""
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["port"] == "8080"
        assert result.outputs["count"] == "42"
        assert result.outputs["ratio"] == "3.14"

    @pytest.mark.asyncio
    async def test_empty_value(self):
        """Test capturing empty values"""
        cmd = """
echo "empty_key=" >> $OFX_OUTPUTS
echo "has_value=something" >> $OFX_OUTPUTS
"""
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs["empty_key"] == ""
        assert result.outputs["has_value"] == "something"

    @pytest.mark.asyncio
    async def test_output_truncated_flag(self):
        """Test that large output sets output_truncated flag"""
        from ofx.settings import settings

        original_max = settings.max_output_size
        settings.max_output_size = 1024
        cmd = 'python3 -c "print(\'x\' * 5000)"'
        ctx = RunContext()

        runner = CommandRunner(Command(cmd=cmd), ctx)
        try:
            result = await runner.run()
            assert result.status == RunnerStatus.COMPLETED
            assert result.outputs.get("output_truncated") is True
        finally:
            settings.max_output_size = original_max
