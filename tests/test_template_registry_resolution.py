"""Tests for template resolution using runner registry data."""

import pytest
import yaml

from ofx.models.workflow import Workflow
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.execution.workflow import WorkflowRunner


@pytest.mark.asyncio
async def test_jobs_and_steps_available_in_templates():
    workflow_yaml = """
name: Template Registry Resolve
jobs:
  producer:
    outputs:
      build_number: "{{ steps.0.outputs.build_number }}"
    steps:
      - run: |
          echo "build_number=12345" >> $OFX_OUTPUTS
  consumer:
    needs: [producer]
    steps:
      - run: |
          echo "value={{ jobs.producer.outputs.build_number }}" >> $OFX_OUTPUTS
      - run: |
          echo "Final value is {{ steps.0.outputs.value }}"
"""
    workflow = Workflow.model_validate(yaml.safe_load(workflow_yaml))
    runner = WorkflowRunner(workflow, RunContext())
    result = await runner.run()

    assert result.status == RunnerStatus.COMPLETED
    producer_runner = runner.runners["producer"]
    consumer_runner = runner.runners["consumer"]

    producer_outputs = await producer_runner.reg_get("outputs")
    assert producer_outputs["build_number"] == "12345"

    consumer_step0 = consumer_runner._runners["0"]
    consumer_outputs = await consumer_step0.reg_get("outputs")
    assert consumer_outputs["value"] == "12345"
