"""Public API for the OFX runner package."""

from ofx.runner.api import run_workflow
from ofx.runner.commands.command import CommandRunner, ScriptRunner
from ofx.runner.context import RunContext, RunnerStatus, RunResult
from ofx.runner.executors.base import Executor
from ofx.runner.executors.cloud import CloudExecutor
from ofx.runner.executors.fleet import FleetExecutor
from ofx.runner.executors.job import JobExecutor
from ofx.runner.executors.matrix import MatrixExecutor
from ofx.runner.executors.pipe import PipeExecutor
from ofx.runner.executors.step import StepExecutor
from ofx.runner.executors.task import TaskExecutor
from ofx.runner.executors.workflow import WorkflowExecutor
from ofx.runner.handlers import HandlerRegistry
from ofx.runner.job import JobRunner, MatrixJobRunner
from ofx.runner.lifecycle import LifecycleManager
from ofx.runner.logging import LogContext, StructuredLogger
from ofx.runner.pipe import PipeRunner
from ofx.runner.registry import RegistryFactory, cleanup_registry
from ofx.runner.registry_adapter import RegistryAdapter
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.runner import BaseRunner, Runner
from ofx.runner.services.event_emitter import EventEmitter
from ofx.runner.step import StepRunner
from ofx.runner.tool_installer import ToolInstallerRunner
from ofx.runner.workflow import WorkflowRunner
from ofx.runner.workflow_execution import ExecutionResult, WorkflowExecutionManager


def create_registry(*, backend: str = "memory", **config):
    """Create a runner registry using the configured backend."""
    return RegistryFactory.create(backend, **config)


__all__ = [
    "CloudExecutor",
    "CommandRunner",
    "BaseRunner",
    "create_registry",
    "cleanup_registry",
    "EventEmitter",
    "Executor",
    "ExecutionResult",
    "FleetExecutor",
    "HandlerRegistry",
    "JobExecutor",
    "JobRunner",
    "LifecycleManager",
    "LogContext",
    "MatrixExecutor",
    "MatrixJobRunner",
    "PipeExecutor",
    "PipeRunner",
    "RegistryAdapter",
    "RegistryFactory",
    "RunContext",
    "RunResult",
    "Runner",
    "RunnerRegistryKeys",
    "RunnerStatus",
    "ScriptRunner",
    "StepExecutor",
    "StepRunner",
    "StructuredLogger",
    "TaskExecutor",
    "ToolInstallerRunner",
    "WorkflowExecutor",
    "WorkflowExecutionManager",
    "WorkflowRunner",
    "run_workflow",
]
