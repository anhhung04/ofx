"""Test script_file and run_file functionality."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from ofx.models.step import Step
from ofx.runner.base import RunContext
from ofx.runner.step import FileRunner, StepRunner


@pytest.mark.asyncio
async def test_python_script_execution():
    """Test executing a Python script with the app's interpreter."""
    # Create a temporary Python script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("#!/usr/bin/env python3\n")
        f.write("import sys\n")
        f.write("print(f'Python: {sys.executable}')\n")
        f.write("print('Hello from Python script')\n")
        script_path = f.name

    try:
        step = Step(
            name="Test Python Script",
            script_file=script_path,
        )

        ctx = RunContext(inputs={}, envs={}, secrets={})
        runner = StepRunner(step, ctx)

        result = await runner.run()

        print(f"Status: {result.status}")
        print(f"Error: {result.error}")
        print(f"Outputs: {result.outputs}")

        assert result.status.value == "completed"
        assert "Hello from Python script" in result.outputs.get("stdout", "")
    finally:
        Path(script_path).unlink()


@pytest.mark.asyncio
async def test_bash_script_execution():
    """Test executing a bash script with shebang."""
    # Create a temporary bash script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/bash\n")
        f.write("echo 'Hello from Bash script'\n")
        f.write("echo $SHELL\n")
        script_path = f.name

    try:
        step = Step(
            name="Test Bash Script",
            run_file=script_path,
        )

        ctx = RunContext(inputs={}, envs={}, secrets={})
        runner = StepRunner(step, ctx)

        result = await runner.run()

        assert result.status.value == "completed"
        assert "Hello from Bash script" in result.outputs.get("stdout", "")
    finally:
        Path(script_path).unlink()


@pytest.mark.asyncio
async def test_python_script_with_imports():
    """Test that Python scripts can import from ofx modules."""
    # Create a Python script that imports ofx modules
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("#!/usr/bin/env python3\n")
        f.write("try:\n")
        f.write("    from ofx.settings import settings\n")
        f.write("    print(f'Successfully imported: {settings.app_branding}')\n")
        f.write("except ImportError as e:\n")
        f.write("    print(f'Import failed: {e}')\n")
        f.write("    exit(1)\n")
        script_path = f.name

    try:
        step = Step(
            name="Test Python Import",
            script_file=script_path,
        )

        ctx = RunContext(inputs={}, envs={}, secrets={})
        runner = StepRunner(step, ctx)

        result = await runner.run()

        assert result.status.value == "completed"
        assert "Successfully imported: ofx" in result.outputs.get("stdout", "")
    finally:
        Path(script_path).unlink()


@pytest.mark.asyncio
async def test_script_not_found():
    """Test error handling when script file is not found."""
    step = Step(
        name="Test Missing Script",
        script_file="/nonexistent/script.py",
    )

    ctx = RunContext(inputs={}, envs={}, secrets={})
    runner = StepRunner(step, ctx)

    result = await runner.run()

    assert result.status.value == "failed"
    assert result.error is not None
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_script_in_search_dirs():
    """Test finding scripts in configured search directories."""
    # Create a script in a custom directory
    temp_dir = Path(tempfile.mkdtemp())
    script_path = temp_dir / "test_script.py"
    script_path.write_text("#!/usr/bin/env python3\n" "print('Found in search dir')\n")

    try:
        # Add the temp directory to search paths
        FileRunner.add_script_dir(temp_dir)

        step = Step(
            name="Test Script Search",
            script_file="test_script.py",
        )

        ctx = RunContext(inputs={}, envs={}, secrets={})
        runner = StepRunner(step, ctx)

        result = await runner.run()

        assert result.status.value == "completed"
        assert "Found in search dir" in result.outputs.get("stdout", "")
    finally:
        script_path.unlink()
        temp_dir.rmdir()


@pytest.mark.asyncio
async def test_relative_script_path():
    """Test executing a script with relative path from working directory."""
    # Create a temporary directory with a script
    temp_dir = Path(tempfile.mkdtemp())
    script_path = temp_dir / "relative_script.py"
    script_path.write_text("#!/usr/bin/env python3\n" "print('Relative path script')\n")

    try:
        step = Step(
            name="Test Relative Path",
            script_file="relative_script.py",
            working_directory=str(temp_dir),
        )

        ctx = RunContext(inputs={}, envs={}, secrets={})
        runner = StepRunner(step, ctx)

        result = await runner.run()

        assert result.status.value == "completed"
        assert "Relative path script" in result.outputs.get("stdout", "")
    finally:
        script_path.unlink()
        temp_dir.rmdir()
