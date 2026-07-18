"""Edge-case tests for OFX model validation."""

import pytest
import yaml
from pydantic import ValidationError

from ofx.models.cloud import CloudConfig
from ofx.models.step import Step
from ofx.models.strategy import MatrixStrategy
from ofx.models.workflow import Workflow

class TestMatrixStrategyValidation:
    """Matrix key identifiers and field constraints."""

    def test_valid_matrix_keys(self):
        ms = MatrixStrategy(matrix={"target": ["a", "b"]})
        assert ms.matrix == {"target": ["a", "b"]}

    def test_valid_underscore_key(self):
        ms = MatrixStrategy(matrix={"my_var": [1, 2]})
        assert ms.matrix == {"my_var": [1, 2]}

    def test_invalid_key_with_hyphen(self):
        with pytest.raises(ValidationError, match="not a valid identifier"):
            MatrixStrategy(matrix={"my-var": [1]})

    def test_invalid_key_with_space(self):
        with pytest.raises(ValidationError, match="not a valid identifier"):
            MatrixStrategy(matrix={"my var": [1]})

    def test_invalid_key_starting_with_digit(self):
        with pytest.raises(ValidationError, match="not a valid identifier"):
            MatrixStrategy(matrix={"1target": [1]})

    def test_empty_matrix_is_valid(self):
        ms = MatrixStrategy(matrix={})
        assert ms.matrix == {}

    def test_max_parallel_zero_rejected(self):
        with pytest.raises(ValidationError):
            MatrixStrategy(max_parallel=0)

    def test_max_parallel_negative_rejected(self):
        with pytest.raises(ValidationError):
            MatrixStrategy(max_parallel=-1)

    def test_max_parallel_one_accepted(self):
        ms = MatrixStrategy(max_parallel=1)
        assert ms.max_parallel == 1

    def test_default_max_parallel_is_four(self):
        ms = MatrixStrategy()
        assert ms.max_parallel == 4

    def test_matrix_value_as_string_template(self):
        """String values in matrix are allowed (resolved at runtime)."""
        ms = MatrixStrategy(matrix={"host": "{{ inputs.targets }}"})
        assert ms.matrix["host"] == "{{ inputs.targets }}"

class TestWorkflowValidation:
    """Workflow-level model validation."""

    def test_needs_nonexistent_job(self):
        with pytest.raises(ValidationError):
            Workflow.model_validate(
                yaml.safe_load(
                    """
name: test
jobs:
  j1:
    needs: [nonexistent]
    steps:
      - run: echo hi
"""
                )
            )

    def test_invalid_job_id_special_chars(self):
        with pytest.raises(ValidationError):
            Workflow.model_validate(
                yaml.safe_load(
                    """
name: test
jobs:
  "job@1":
    steps:
      - run: echo hi
"""
                )
            )

    def test_valid_job_id_with_hyphen_and_underscore(self):
        wf = Workflow.model_validate(
            yaml.safe_load(
                """
name: test
jobs:
  my-job_1:
    steps:
      - run: echo hi
"""
            )
        )
        assert "my-job_1" in wf.jobs

    def test_conflicting_run_types_in_step(self):
        with pytest.raises(ValidationError):
            Workflow.model_validate(
                yaml.safe_load(
                    """
name: test
jobs:
  j1:
    steps:
      - run: echo hi
        script: print('hi')
"""
                )
            )

    def test_step_with_no_run_type(self):
        with pytest.raises(ValidationError):
            Workflow.model_validate(
                yaml.safe_load(
                    """
name: test
jobs:
  j1:
    steps:
      - name: empty-step
"""
                )
            )

    def test_matrix_string_template_in_workflow(self):
        """Matrix values as a string template should succeed."""
        wf = Workflow.model_validate(
            yaml.safe_load(
                """
name: test
jobs:
  j1:
    strategy:
      matrix:
        host: "{{ inputs.targets }}"
    steps:
      - run: echo hi
"""
            )
        )
        assert wf.jobs["j1"].strategy is not None
        assert wf.jobs["j1"].strategy.matrix["host"] == "{{ inputs.targets }}"

    def test_circular_dependency_detected(self):
        with pytest.raises(ValidationError):
            Workflow.model_validate(
                yaml.safe_load(
                    """
name: test
jobs:
  a:
    needs: [b]
    steps:
      - run: echo a
  b:
    needs: [a]
    steps:
      - run: echo b
"""
                )
            )

    def test_workflow_must_have_at_least_one_job(self):
        with pytest.raises(ValidationError):
            Workflow.model_validate(
                yaml.safe_load(
                    """
name: test
jobs: {}
"""
                )
            )

class TestStepValidation:
    """Step-level field constraints."""

    def test_valid_run_step(self):
        step = Step.model_validate({"run": "echo hello"})
        assert step.run == "echo hello"

    def test_valid_script_step(self):
        step = Step.model_validate({"script": "print('hi')"})
        assert step.script == "print('hi')"

    def test_valid_task_step(self):
        step = Step.model_validate({"task": "nmap", "with": {"target": "127.0.0.1"}})
        assert step.task == "nmap"

    def test_both_run_and_script_raises(self):
        with pytest.raises(ValidationError, match="exactly one"):
            Step.model_validate({"run": "echo hi", "script": "print('hi')"})

    def test_no_run_type_raises(self):
        with pytest.raises(ValidationError, match="exactly one"):
            Step.model_validate({"name": "empty"})

    def test_negative_retry_raises(self):
        with pytest.raises(ValidationError):
            Step.model_validate({"run": "echo hi", "retry": -1})

    def test_negative_timeout_raises(self):
        with pytest.raises(ValidationError):
            Step.model_validate({"run": "echo hi", "timeout": -1})

    def test_zero_timeout_raises(self):
        with pytest.raises(ValidationError):
            Step.model_validate({"run": "echo hi", "timeout": 0})

    def test_negative_retry_delay_raises(self):
        with pytest.raises(ValidationError):
            Step.model_validate({"run": "echo hi", "retry-delay": -1})

class TestCloudConfigValidation:
    """CloudConfig defaults and normalization."""

    def test_valid_static_config(self):
        cfg = CloudConfig(provider="static", host="10.0.0.1")
        assert cfg.provider == "static"
        assert cfg.host == "10.0.0.1"

    def test_valid_config_with_ssh_host(self):
        cfg = CloudConfig(host="192.168.1.10", ssh_user="admin", ssh_port=2222)
        assert cfg.ssh_user == "admin"
        assert cfg.ssh_port == 2222

    def test_default_ssh_port(self):
        cfg = CloudConfig()
        assert cfg.ssh_port == 22

    def test_default_os_is_linux(self):
        cfg = CloudConfig()
        assert cfg.os == "linux"

    def test_windows_auto_sets_winrm_connection(self):
        cfg = CloudConfig(os="windows")
        assert cfg.connection_type == "winrm"

    def test_winrm_ssl_auto_sets_port(self):
        cfg = CloudConfig(os="windows", winrm_ssl=True)
        assert cfg.winrm_port == 5986

    def test_provider_auto_detected_from_host(self):
        cfg = CloudConfig(host="10.0.0.5")
        assert cfg.provider == "static"

    def test_extra_fields_allowed(self):
        """CloudConfig uses extra='allow' unlike other models."""
        cfg = CloudConfig(custom_field="value")
        assert cfg.custom_field == "value"
