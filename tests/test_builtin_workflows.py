"""Static contract tests for the complete builtin workflow catalogue.

These run without any external tooling: every builtin workflow must parse,
load through the real loader, resolve each module reference and each ``uses:``
target, and honour the reusable-workflow contract that parent steps rely on
(``call.inputs`` for everything passed via ``with:`` and ``call.outputs`` for
everything a parent reads back). Without that contract parent references
silently resolve to empty strings at runtime.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from ofx.modules.registry import ModuleRegistry
from ofx.settings import BUILTIN_WORKFLOWS_DIR
from ofx.utils.workflow_utils import find_workflow

WORKFLOWS_DIR = Path(BUILTIN_WORKFLOWS_DIR)
WORKFLOW_FILES = sorted(WORKFLOWS_DIR.rglob("*.yml"))
WORKFLOW_IDS = [
    str(path.relative_to(WORKFLOWS_DIR).with_suffix("")) for path in WORKFLOW_FILES
]

# Jinja parses ``steps.foo-bar.outputs.x`` as a subtraction and raises
# UndefinedError, so dashed step/job names must be indexed (``steps['foo-bar']``).
_DOTTED_DASH_RE = re.compile(r"\b(?:steps|jobs)\.([A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)+)\.")
_INDEXED_OUTPUT_RE = re.compile(r"\b(?:steps|jobs)\['([^']+)'\]\.outputs\.([A-Za-z0-9_]+)")
_DOTTED_OUTPUT_RE = re.compile(r"\b(?:steps|jobs)\.([A-Za-z0-9_]+)\.outputs\.([A-Za-z0-9_]+)")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _yaml(path: Path) -> dict:
    return yaml.safe_load(_read(path))


def _steps(data: dict):
    for job_id, job in (data.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            yield job_id, step


def _reused_steps(data: dict):
    for _job_id, step in _steps(data):
        if step.get("uses"):
            yield step


def _referenced_outputs(text: str) -> set[tuple[str, str]]:
    """Return every ``<owner>.<name>.outputs.<key>`` reference in a workflow."""
    refs = {(owner, key) for owner, key in _INDEXED_OUTPUT_RE.findall(text)}
    refs.update((owner, key) for owner, key in _DOTTED_OUTPUT_RE.findall(text))
    return refs


def test_catalogue_contains_every_builtin_workflow():
    assert len(WORKFLOW_FILES) >= 46
    assert len(WORKFLOW_IDS) == len(set(WORKFLOW_IDS))
    categories = {path.parent.name for path in WORKFLOW_FILES}
    assert {"recon", "scan"} <= categories


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_workflow_yaml_parses(workflow_path: Path):
    data = _yaml(workflow_path)
    assert isinstance(data, dict), f"{workflow_path} did not parse to a mapping"
    assert data.get("name"), f"{workflow_path} has no name"
    jobs = data.get("jobs")
    assert isinstance(jobs, dict) and jobs, f"{workflow_path} has no jobs"
    for job_id, job in jobs.items():
        assert job.get("steps"), f"{workflow_path}: job {job_id} has no steps"


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_workflow_loads_through_the_real_loader(workflow_path: Path):
    workflow_id = str(workflow_path.relative_to(WORKFLOWS_DIR).with_suffix(""))
    workflow = find_workflow(workflow_id, (WORKFLOWS_DIR,))
    assert workflow.name
    assert workflow.jobs
    assert workflow.workflow_path == workflow_path


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_every_module_reference_resolves(workflow_path: Path):
    registry = ModuleRegistry(workflow_dir=workflow_path.parent)
    data = _yaml(workflow_path)
    for job_id, step in _steps(data):
        spec = step.get("module")
        if not spec:
            continue
        resolved = registry.resolve(spec)
        assert resolved.callable is not None, (
            f"{workflow_path}: {job_id}/{step.get('name')} module {spec!r} "
            "did not resolve to a callable"
        )


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_every_reused_workflow_resolves(workflow_path: Path):
    data = _yaml(workflow_path)
    for job_id, step in _steps(data):
        target = step.get("uses")
        if not target:
            continue
        resolved = find_workflow(target, (WORKFLOWS_DIR,))
        assert resolved.name, (
            f"{workflow_path}: {job_id}/{step.get('name')} uses {target!r} "
            "which did not resolve to a workflow"
        )


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_dashed_step_and_job_names_use_index_syntax(workflow_path: Path):
    offenders = sorted({match.group(1) for match in _DOTTED_DASH_RE.finditer(_read(workflow_path))})
    assert not offenders, (
        f"{workflow_path}: dashed names must be indexed (steps['name']), got {offenders}"
    )


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_reused_workflows_declare_a_call_contract(workflow_path: Path):
    data = _yaml(workflow_path)
    for step in _reused_steps(data):
        target = step["uses"]
        callee = _yaml(WORKFLOWS_DIR / f"{target}.yml")
        call = callee.get("call") or {}
        assert call.get("inputs"), f"{target} declares no call.inputs"
        assert call.get("outputs"), f"{target} declares no call.outputs"


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_reused_call_inputs_declare_every_passed_argument(workflow_path: Path):
    data = _yaml(workflow_path)
    for job_id, step in _steps(data):
        target = step.get("uses")
        if not target:
            continue
        declared = set(
            (_yaml(WORKFLOWS_DIR / f"{target}.yml").get("call") or {}).get("inputs") or {}
        )
        passed = set(step.get("with") or {})
        undeclared = sorted(passed - declared)
        assert not undeclared, (
            f"{workflow_path}: {job_id}/{step.get('name')} passes {undeclared} to "
            f"{target} which does not declare them in call.inputs"
        )


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=WORKFLOW_IDS)
def test_reused_call_outputs_cover_parent_references(workflow_path: Path):
    data = _yaml(workflow_path)
    reused = {step["name"]: step["uses"] for step in _reused_steps(data)}
    if not reused:
        return
    available = {}
    for name, target in reused.items():
        callee_call = _yaml(WORKFLOWS_DIR / f"{target}.yml").get("call") or {}
        available[name] = set(callee_call.get("outputs") or {})
    for owner, key in sorted(_referenced_outputs(_read(workflow_path))):
        if owner not in reused:
            continue
        assert key in available[owner], (
            f"{workflow_path}: references {owner}.outputs.{key} but {reused[owner]} "
            f"only promotes {sorted(available[owner])}"
        )
