"""Models for OFX workflow execution.

This module provides Pydantic models for defining and running workflows.

Usage:
    from ofx.models import Workflow, Job, Step
    from ofx.models import Command, Script
    from ofx.models import WorkflowInput, WorkflowSecret
"""

from ofx.models.base import OFXBaseModel
from ofx.models.cloud import (
    CloudConfig,
    CloudHostEntry,
    parse_cloud_field,
)
from ofx.models.command import Command, Script
from ofx.models.config import DefaultConfig, RunConfig
from ofx.models.inputs import WorkflowInput, WorkflowSecret
from ofx.models.job import Job
from ofx.models.step import RunType, Step
from ofx.models.strategy import FleetStrategy, MatrixStrategy
from ofx.models.tools import ToolConfig
from ofx.models.workflow import Workflow, WorkflowCall, WorkflowDispatch

__all__ = [
    # Base
    "OFXBaseModel",
    # Cloud
    "CloudConfig",
    "CloudHostEntry",
    "FleetStrategy",
    "parse_cloud_field",
    # Config
    "DefaultConfig",
    "RunConfig",
    # Command
    "Command",
    "Script",
    # Inputs
    "WorkflowInput",
    "WorkflowSecret",
    # Strategy
    "MatrixStrategy",
    # Tools
    "ToolConfig",
    # Step
    "Step",
    "RunType",
    # Job
    "Job",
    # Workflow
    "Workflow",
    "WorkflowCall",
    "WorkflowDispatch",
]
