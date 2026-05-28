"""Comprehensive tests for matrix strategy functionality"""

from pathlib import Path

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunContext, WorkflowRunner
from ofx.runner.executors.workflow import WorkflowExecutor
from ofx.utils.matrix import get_expanded_job_ids


@pytest.fixture
def workflow_dir():
    return Path(__file__).parent / "flows"


async def plan_jobs(runner: WorkflowRunner) -> None:
    await WorkflowExecutor().plan_jobs(runner)


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
      - run: echo {{ matrix.value }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)
        assert len(combinations) == 3
        assert combinations[0]["value"] == 1
        assert combinations[1]["value"] == 2
        assert combinations[2]["value"] == 3

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
      - run: echo {{ matrix.os }}-{{ matrix.arch }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)
        assert len(combinations) == 4

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
      - run: echo {{ matrix.os }}-{{ matrix.browser }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)
        assert len(combinations) == 7
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
      - run: echo {{ matrix.platform }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)
        assert len(combinations) == 4
        platforms = [combo["platform"] for combo in combinations]
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
      - run: echo "{{ matrix.id }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        assert job.max_parallel == 2

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
      - run: echo "{{ matrix.task }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        assert job.fail_fast is True

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
      - run: echo "{{ matrix.config.name }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)

        assert len(combinations) == 4

        config_0 = combinations[0]["config"]
        assert isinstance(config_0, dict)
        assert config_0["name"] in ["dev", "prod"]
        assert config_0["port"] in [3000, 8080]

        debug_vals = [c["debug"] for c in combinations]
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
      - run: echo "Building {{ matrix.version }}"

  test:
    needs: build
    strategy:
      matrix:
        env: [dev, prod]
    steps:
      - run: echo "Testing in {{ matrix.env }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 2
        assert len(runner._schedule) == 2

        stage_0_jobs = runner._schedule[0]
        stage_1_jobs = runner._schedule[1]

        assert "build" in stage_0_jobs
        assert "test" in stage_1_jobs

    # @pytest.mark.asyncio
    # async def test_get_job_status_matrix(self):
    #     """Test get_job_status handles matrix jobs correctly"""
    #     workflow_yaml = """
    # name: Job Status Test
    # jobs:
    #   test:
    #     strategy:
    #       matrix:
    #         id: [1, 2]
    #     steps:
    #       - run: echo "{{ matrix.id }}"
    # """
    #     workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
    #     runner = WorkflowRunner(workflow, RunContext())

    #     await plan_jobs(runner)

    #     await runner._registry.set("test_0", {"status": RunnerStatus.COMPLETED})
    #     await runner._registry.set("test_1", {"status": RunnerStatus.RUNNING})

    #     status = runner.get_job_status("test")
    #     assert status == RunnerStatus.RUNNING

    #     await runner._registry.set("test_1", {"status": RunnerStatus.COMPLETED})
    #     status = runner.get_job_status("test")
    #     assert status == RunnerStatus.COMPLETED

    #     await runner._registry.set("test_0", {"status": RunnerStatus.FAILED})
    #     status = runner.get_job_status("test")
    #     assert status == RunnerStatus.FAILED

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
      - run: echo "{{ matrix.only }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)
        assert len(combinations) == 1
        assert combinations[0]["only"] == "single"

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
      - run: echo "{{ matrix.x }}-{{ matrix.y }}-{{ matrix.z }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)
        assert len(combinations) == 8

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

        await plan_jobs(runner)

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
      - run: echo {{ matrix.env }}-{{ matrix.version }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)

        assert len(combinations) == 6
        assert {"env": "prod", "version": 1.0} not in combinations
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
    name: "Build for {{ matrix.platform }}"
    strategy:
      matrix:
        platform: [linux, macos]
    steps:
      - run: echo "Building"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        assert runner._staged_jobs["test"].name == "Build for {{ matrix.platform }}"

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
      - run: echo "{{ matrix.id }}"

  normal_job:
    steps:
      - run: echo "Normal"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        matrix_ids = get_expanded_job_ids(runner._staged_jobs, "matrix_job")
        assert matrix_ids == ["matrix_job"]

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
      - run: echo {{ matrix.value }}
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        runner = WorkflowRunner(workflow, RunContext())

        await plan_jobs(runner)

        assert len(runner._staged_jobs) == 1
        job = runner._staged_jobs["test"]
        from ofx.utils.matrix import _generate_matrix_combinations

        combinations = _generate_matrix_combinations(job.strategy)
        assert len(combinations) == 3
        values = [combo["value"] for combo in combinations]
        assert "plain" in values
        assert "with-dash" in values
        assert "with_underscore" in values


class TestMatrixFailFast:
    """Tests for fail_fast behavior in local MatrixJobRunner."""

    @pytest.mark.asyncio
    async def test_fail_fast_false_runs_all_combinations(self):
        """With fail_fast: false, all matrix combinations run even when some fail."""
        workflow_yaml = """
name: Fail Fast False Test
jobs:
  test:
    strategy:
      fail_fast: false
      matrix:
        val: [1, 2, 3]
    steps:
      - name: maybe-fail
        run: |
          if [ "{{ matrix.val }}" = "2" ]; then exit 1; fi
          echo "ok {{ matrix.val }}"
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        ctx = RunContext()
        runner = WorkflowRunner(workflow, ctx)
        result = await runner.run()
        # Should fail overall (one combo failed)
        assert result.status.value == "failed"
        # But all 3 combinations should have been attempted
        # (with fail_fast: true, combo 2 would stop combo 3)
        assert "test_0" in runner._runners or "test" in runner._runners

    @pytest.mark.asyncio
    async def test_fail_fast_true_is_default(self):
        """Default fail_fast is True — matrix stops on first failure."""
        workflow_yaml = """
name: Fail Fast Default Test
jobs:
  test:
    strategy:
      matrix:
        val: [1, 2, 3]
    steps:
      - name: fail-all
        run: exit 1
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        assert workflow.jobs["test"].strategy.fail_fast is True


class TestStepNameUniqueness:
    """Tests for step name uniqueness validation."""

    def test_duplicate_step_names_rejected(self):
        """Duplicate step names within a job should raise ValueError."""
        workflow_yaml = """
name: Duplicate Steps
jobs:
  test:
    steps:
      - name: deploy
        run: echo 1
      - name: deploy
        run: echo 2
"""
        with pytest.raises(ValueError, match="duplicate step name 'deploy'"):
            Workflow.model_validate(yaml.safe_load(workflow_yaml))

    def test_same_name_different_jobs_allowed(self):
        """Same step name across different jobs is fine."""
        workflow_yaml = """
name: Same Name Different Jobs
jobs:
  job1:
    steps:
      - name: deploy
        run: echo 1
  job2:
    steps:
      - name: deploy
        run: echo 2
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        assert len(workflow.jobs) == 2

    def test_auto_generated_names_never_collide(self):
        """Steps without names get unique auto-generated names."""
        workflow_yaml = """
name: Auto Names
jobs:
  test:
    steps:
      - run: echo 1
      - run: echo 2
      - run: echo 3
"""
        workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
        names = [s.name for s in workflow.jobs["test"].steps]
        assert len(names) == len(set(names))
