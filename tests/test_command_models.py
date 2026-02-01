"""Tests for command and script models"""

from pathlib import Path

from ofx.models.command import Command, Script
from ofx.settings import DEFAULT_SHELL


class TestCommandModel:
    """Test Command model"""

    def test_command_creation_minimal(self):
        """Test creating a Command with minimal required fields"""
        cmd = Command(cmd="echo hello")
        assert cmd.cmd == "echo hello"
        assert cmd.shell == DEFAULT_SHELL
        assert cmd.working_directory == Path.cwd()
        assert cmd.timeout_minutes == 1440
        assert cmd.interactive is False

    def test_command_creation_full(self):
        """Test creating a Command with all fields"""
        cmd = Command(
            cmd="ls -la",
            shell="/bin/bash",
            working_directory=Path("/tmp"),
            timeout_minutes=60,
            interactive=True,
        )
        assert cmd.cmd == "ls -la"
        assert cmd.shell == "/bin/bash"
        assert cmd.working_directory == Path("/tmp")
        assert cmd.timeout_minutes == 60
        assert cmd.interactive is True

    def test_command_str(self):
        """Test Command __str__ command"""
        cmd = Command(cmd="echo hello")
        result = str(cmd)
        assert "Command(cmd=" in result
        assert "echo" in result

    def test_command_model_dump(self):
        """Test Command model_dump"""
        cmd = Command(cmd="test", shell="/bin/sh")
        dumped = cmd.model_dump()
        assert dumped["cmd"] == "test"
        assert dumped["shell"] == "/bin/sh"
        assert "working_directory" in dumped

    def test_command_model_validate(self):
        """Test Command model validation"""
        cmd_dict = {
            "cmd": "test command",
            "shell": "/bin/bash",
        }
        cmd = Command.model_validate(cmd_dict)
        assert cmd.cmd == "test command"
        assert cmd.shell == "/bin/bash"


class TestScriptModel:
    """Test Script model"""

    def test_script_creation_minimal(self):
        """Test creating a Script with minimal required fields"""
        script = Script(script="print('hello')")
        assert script.script == "print('hello')"
        assert script.shell == DEFAULT_SHELL
        assert script.working_directory == Path.cwd()
        assert script.timeout_minutes == 1440
        assert script.interactive is False

    def test_script_creation_full(self):
        """Test creating a Script with all fields"""
        script = Script(
            script="import sys; print(sys.version)",
            shell="/bin/bash",
            working_directory=Path("/tmp"),
            timeout_minutes=30,
            interactive=True,
        )
        assert script.script == "import sys; print(sys.version)"
        assert script.shell == "/bin/bash"
        assert script.working_directory == Path("/tmp")
        assert script.timeout_minutes == 30
        assert script.interactive is True

    def test_script_str_short(self):
        """Test Script __str__ with short script"""
        script = Script(script="print('test')")
        assert "Script(inline," in str(script)

    def test_script_model_dump(self):
        """Test Script model_dump"""
        script = Script(script="test script", timeout_minutes=120)
        dumped = script.model_dump()
        assert dumped["script"] == "test script"
        assert dumped["timeout_minutes"] == 120

    def test_script_model_validate(self):
        """Test Script model validation"""
        script_dict = {
            "script": "import os; os.getcwd()",
            "interactive": True,
        }
        script = Script.model_validate(script_dict)
        assert script.script == "import os; os.getcwd()"
        assert script.interactive is True
