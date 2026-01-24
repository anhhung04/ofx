"""Comprehensive tests for matrix strategy functionality"""

from pathlib import Path

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
from ofx.utils.matrix import get_expanded_job_ids


@pytest.fixture
def workflow_dir():
    return Path(__file__).parent / "flows"


class TestMatrixStrategy:
    """Test suite for matrix strategy features"""

    @pytest.mark.asyncio
    async def test_basic_matrix_expansion(self):
        workflow_yaml = """
name: Basic Matrix Test
jobs:
  test:
    strategy:
      matrix:
        value: [1, 2, 3]
    steps:
      - run: echo ${{ matrix.value }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 3
        assert "test_0" in runner._staged_jobs
        assert "test_1" in runner._staged_jobs
        assert "test_2" in runner._staged_jobs
        assert runner._staged_jobs["test_0"].matrix_values["value"] == 1
        assert runner._staged_jobs["test_1"].matrix_values["value"] == 2
        assert runner._staged_jobs["test_2"].matrix_values["value"] == 3

    @pytest.mark.asyncio
    async def test_multi_dimensional_matrix(self):
        workflow_yaml = """
name: Multi-dimensional Matrix
jobs:
  test:
    strategy:
      matrix:
        os: [linux, macos]
        arch: [amd64, arm64]
    steps:
      - run: echo ${{ matrix.os }}-${{ matrix.arch }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 4
        combinations = [
            runner._staged_jobs[f"test_{i}"].matrix_values for i in range(4)
        ]

        assert {"os": "linux", "arch": "amd64"} in combinations
        assert {"os": "linux", "arch": "arm64"} in combinations
        assert {"os": "macos", "arch": "amd64"} in combinations
        assert {"os": "macos", "arch": "arm64"} in combinations

    @pytest.mark.asyncio
    async def test_matrix_with_exclude(self):
        workflow_yaml = """
name: Matrix Exclude Test
jobs:
  test:
    strategy:
      matrix:
        os: [linux, macos, windows]
        browser: [chrome, firefox, safari]
      exclude:
        - os: linux
          browser: safari
        - os: windows
          browser: safari
    steps:
      - run: echo ${{ matrix.os }}-${{ matrix.browser }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 7
        combinations = [
            runner._staged_jobs[f"test_{i}"].matrix_values for i in range(7)
        ]

        assert {"os": "linux", "browser": "safari"} not in combinations
        assert {"os": "windows", "browser": "safari"} not in combinations
        assert {"os": "macos", "browser": "safari"} in combinations

    @pytest.mark.asyncio
    async def test_matrix_with_include(self):
        workflow_yaml = """
name: Matrix Include Test
jobs:
  test:
    strategy:
      matrix:
        platform: [x86, x64]
      include:
        - platform: arm64
        - platform: riscv
    steps:
      - run: echo ${{ matrix.platform }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 4
        platforms = [
            runner._staged_jobs[f"test_{i}"].matrix_values["platform"] for i in range(4)
        ]

        assert "x86" in platforms
        assert "x64" in platforms
        assert "arm64" in platforms
        assert "riscv" in platforms

    @pytest.mark.asyncio
    async def test_matrix_max_parallel(self):
        """Test max_parallel creates semaphore with correct limit"""
        workflow_yaml = """
name: Max Parallel Test
jobs:
  test:
    strategy:
      max_parallel: 2
      matrix:
        id: [1, 2, 3, 4, 5]
    steps:
      - run: echo "${{ matrix.id }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 5
        for i in range(5):
            assert runner._staged_jobs[f"test_{i}"].max_parallel == 2

    @pytest.mark.asyncio
    async def test_matrix_fail_fast_flag(self):
        """Test fail_fast flag is captured in expanded jobs"""
        workflow_yaml = """
name: Fail Fast Test
jobs:
  test:
    strategy:
      fail_fast: true
      matrix:
        task: [a, b, c]
    steps:
      - run: echo "${{ matrix.task }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        for i in range(3):
            assert runner._staged_jobs[f"test_{i}"].fail_fast is True

    @pytest.mark.asyncio
    async def test_matrix_json_value_parsing(self):
        """Test JSON values in matrix are parsed correctly"""
        workflow_yaml = """
name: JSON Matrix Test
jobs:
  test:
    strategy:
      matrix:
        config: ['{"name": "dev", "port": 3000}', '{"name": "prod", "port": 8080}']
        debug: ["true", "false"]
    steps:
      - run: echo "${{ matrix.config.name }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 4

        config_0 = runner._staged_jobs["test_0"].matrix_values["config"]
        assert isinstance(config_0, dict)
        assert config_0["name"] in ["dev", "prod"]
        assert config_0["port"] in [3000, 8080]

        debug_vals = [
            runner._staged_jobs[f"test_{i}"].matrix_values["debug"] for i in range(4)
        ]
        assert True in debug_vals
        assert False in debug_vals

    @pytest.mark.asyncio
    async def test_matrix_dependencies(self):
        """Test dependencies work correctly with matrix expansion"""
        workflow_yaml = """
name: Matrix Dependencies Test
jobs:
  build:
    strategy:
      matrix:
        version: [1, 2]
    steps:
      - run: echo "Building ${{ matrix.version }}"
  
  test:
    needs: build
    strategy:
      matrix:
        env: [dev, prod]
    steps:
      - run: echo "Testing in ${{ matrix.env }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 4
        assert len(runner._schedule) == 2

        stage_0_jobs = runner._schedule[0]
        stage_1_jobs = runner._schedule[1]

        assert "build_0" in stage_0_jobs
        assert "build_1" in stage_0_jobs
        assert "test_0" in stage_1_jobs
        assert "test_1" in stage_1_jobs

    @pytest.mark.asyncio
    async def test_get_job_status_matrix(self):
        """Test get_job_status handles matrix jobs correctly"""
        workflow_yaml = """
name: Job Status Test
jobs:
  test:
    strategy:
      matrix:
        id: [1, 2]
    steps:
      - run: echo "${{ matrix.id }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        await runner._job_registry.set("test_0", {"status": RunnerStatus.COMPLETED})
        await runner._job_registry.set("test_1", {"status": RunnerStatus.RUNNING})

        status = runner.get_job_status("test")
        assert status == RunnerStatus.RUNNING

        await runner._job_registry.set("test_1", {"status": RunnerStatus.COMPLETED})
        status = runner.get_job_status("test")
        assert status == RunnerStatus.COMPLETED

        await runner._job_registry.set("test_0", {"status": RunnerStatus.FAILED})
        status = runner.get_job_status("test")
        assert status == RunnerStatus.FAILED

    @pytest.mark.asyncio
    async def test_single_value_matrix(self):
        """Test matrix with single value still expands"""
        workflow_yaml = """
name: Single Value Matrix
jobs:
  test:
    strategy:
      matrix:
        only: [single]
    steps:
      - run: echo "${{ matrix.only }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 1
        assert runner._staged_jobs["test_0"].matrix_values["only"] == "single"

    @pytest.mark.asyncio
    async def test_three_dimensional_matrix(self):
        """Test matrix with three dimensions"""
        workflow_yaml = """
name: 3D Matrix Test
jobs:
  test:
    strategy:
      matrix:
        x: [1, 2]
        y: [a, b]
        z: [true, false]
    steps:
      - run: echo "${{ matrix.x }}-${{ matrix.y }}-${{ matrix.z }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 8

    @pytest.mark.asyncio
    async def test_matrix_without_strategy(self):
        """Test job without strategy is still added to expanded jobs"""
        workflow_yaml = """
name: No Strategy Test
jobs:
  test:
    steps:
      - run: echo "No matrix"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 1
        assert "test" in runner._staged_jobs
        assert runner._staged_jobs["test"].matrix_values == {}

    @pytest.mark.asyncio
    async def test_complex_exclude_include(self):
        workflow_yaml = """
name: Complex Filter Test
jobs:
  test:
    strategy:
      matrix:
        env: [dev, staging, prod]
        version: ["1.0", "2.0"]
      exclude:
        - env: prod
          version: "1.0"
      include:
        - env: canary
          version: "2.0"
    steps:
      - run: echo ${{ matrix.env }}-${{ matrix.version }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 6
        combinations = [
            runner._staged_jobs[f"test_{i}"].matrix_values for i in range(6)
        ]

        assert {"env": "prod", "version": "1.0"} not in combinations
        canary_found = any(
            c.get("env") == "canary" and c.get("version") == 2.0 for c in combinations
        )
        assert canary_found, f"Canary not found in combinations: {combinations}"

    @pytest.mark.asyncio
    async def test_matrix_name_templating(self):
        """Test job names can use matrix values"""
        workflow_yaml = """
name: Name Template Test
jobs:
  test:
    name: "Build for ${{ matrix.platform }}"
    strategy:
      matrix:
        platform: [linux, macos]
    steps:
      - run: echo "Building"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert runner._staged_jobs["test_0"].name == "Build for linux"
        assert runner._staged_jobs["test_1"].name == "Build for macos"

    @pytest.mark.asyncio
    async def test_get_expanded_job_ids(self):
        """Test _get_expanded_job_ids returns correct IDs"""
        workflow_yaml = """
name: Expanded IDs Test
jobs:
  matrix_job:
    strategy:
      matrix:
        id: [1, 2, 3]
    steps:
      - run: echo "${{ matrix.id }}"
  
  normal_job:
    steps:
      - run: echo "Normal"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        matrix_ids = get_expanded_job_ids(runner._staged_jobs, "matrix_job")
        assert len(matrix_ids) == 3
        assert "matrix_job_0" in matrix_ids
        assert "matrix_job_1" in matrix_ids
        assert "matrix_job_2" in matrix_ids

        normal_ids = get_expanded_job_ids(runner._staged_jobs, "normal_job")
        assert normal_ids == ["normal_job"]

    @pytest.mark.asyncio
    async def test_matrix_value_parsing_strings(self):
        workflow_yaml = """
name: String Parsing Test
jobs:
  test:
    strategy:
      matrix:
        value: ["plain", "with-dash", "with_underscore"]
    steps:
      - run: echo ${{ matrix.value }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await runner._plan_jobs()

        assert len(runner._staged_jobs) == 3
        values = [
            runner._staged_jobs[f"test_{i}"].matrix_values["value"] for i in range(3)
        ]
        assert "plain" in values
        assert "with-dash" in values
        assert "with_underscore" in values
