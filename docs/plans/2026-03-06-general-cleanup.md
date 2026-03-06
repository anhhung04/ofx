# General Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Perform a broad codebase cleanup to improve readability, reduce duplication, and adhere to linting/formatting standards.

**Architecture:** The cleanup touches multiple layers: CLI command modules, runner core, and cloud provider abstractions. We'll make incremental, isolated edits, each with its own test (where applicable) and commit.

**Tech Stack:** Python 3.10+, `ruff` for linting/formatting, `mypy` for type checking, `pytest` for tests.

---

### Task 1: Run linter and formatter locally

**Files:**
- Modify: `none`
- Test: `none`

**Step 1: Write the failing test** (no test needed).

**Step 2: Run test to verify it fails** (skip).

**Step 3: Run lint and format**

```bash
uv run ruff check src/ --fix
uv run ruff format src/
```

**Step 4: Verify no lint errors**

```bash
uv run ruff check src/
```

**Step 5: Commit**

```bash
git add .
git commit -m "style: apply ruff auto-fix and format"
```

---

### Task 2: Remove dead code in `src/ofx/commands/cloud/app.py`

**Files:**
- Modify: `src/ofx/commands/cloud/app.py:1-200`
- Test: `tests/ofx/commands/cloud/test_app.py`

**Step 1: Write the failing test**

```python
def test_unused_helper_removed():
    from src.ofx.commands.cloud.app import _unused_helper
    assert hasattr(_unused_helper, '__call__')
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/ofx/commands/cloud/test_app.py::test_unused_helper_removed -v
```

**Step 3: Delete the dead function** (remove `_unused_helper` definition and any imports).

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/ofx/commands/cloud/test_app.py::test_unused_helper_removed -v
```

**Step 5: Commit**

```bash
git add src/ofx/commands/cloud/app.py tests/ofx/commands/cloud/test_app.py
git commit -m "refactor: remove dead helper from cloud app"
```

---

### Task 3: Consolidate duplicated logging setup in runner core

**Files:**
- Modify: `src/ofx/runner/execution/base.py:50-80`
- Modify: `src/ofx/runner/execution/job.py:30-60`
- Test: `tests/ofx/runner/execution/test_logging.py`

**Step 1: Write the failing test**

```python
from src.ofx.runner.execution.base import BaseRunner

def test_logger_is_shared():
    r1 = BaseRunner()
    r2 = BaseRunner()
    assert r1.logger is r2.logger
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/ofx/runner/execution/test_logging.py::test_logger_is_shared -v
```

**Step 3: Extract common logger creation to `src/ofx/runner/logging.py` and import it**

```python
# src/ofx/runner/logging.py
import logging

def get_shared_logger(name: str = "ofx") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

Update `base.py` and `job.py` to `from .logging import get_shared_logger` and use `self.logger = get_shared_logger(__name__)`.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/ofx/runner/execution/test_logging.py::test_logger_is_shared -v
```

**Step 5: Commit**

```bash
git add src/ofx/runner/logging.py src/ofx/runner/execution/base.py src/ofx/runner/execution/job.py tests/ofx/runner/execution/test_logging.py
git commit -m "refactor: centralize logger creation"
```

---

### Task 4: Simplify Cloud fleet chunk handling in `src/ofx/cloud/fleet_distributor.py`

**Files:**
- Modify: `src/ofx/cloud/fleet_distributor.py:120-170`
- Test: `tests/ofx/cloud/test_fleet_distributor.py`

**Step 1: Write the failing test**

```python
from src.ofx.cloud.fleet_distributor import expand_fleet_to_matrix

def test_expand_fleet_simple():
    fleet = {"count": 2, "input": ["10.0.0.1", "10.0.0.2"]}
    matrix = expand_fleet_to_matrix(fleet)
    assert len(matrix) == 2
    assert matrix[0]["host"] == "10.0.0.1"
    assert matrix[1]["host"] == "10.0.0.2"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/ofx/cloud/test_fleet_distributor.py::test_expand_fleet_simple -v
```

**Step 3: Refactor `expand_fleet_to_matrix` to use list comprehension and remove unnecessary temp files** (code omitted for brevity).

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/ofx/cloud/test_fleet_distributor.py::test_expand_fleet_simple -v
```

**Step 5: Commit**

```bash
git add src/ofx/cloud/fleet_distributor.py tests/ofx/cloud/test_fleet_distributor.py
git commit -m "refactor: simplify fleet matrix expansion"
```

---

### Task 5: Update documentation index for cleanup

**Files:**
- Modify: `docs/README.md`
- Test: `none`

**Step 1: Write the failing test** (skip).

**Step 2: Run test to verify it fails** (skip).

**Step 3: Add a "General Cleanup" section describing the recent refactors**

```markdown
## General Cleanup (2026-03-06)
- Applied `ruff` auto‑fix and formatting.
- Removed dead code from cloud command module.
- Centralized logger creation.
- Simplified fleet matrix expansion.
```

**Step 4: Run the tests to verify all still pass**

```bash
uv run pytest -q
```

**Step 5: Commit**

```bash
git add docs/README.md
git commit -m "docs: add General Cleanup summary"
```

---

**Plan complete and saved to `docs/plans/2026-03-06-general-cleanup.md`.**

Two execution options:

1. **Subagent-Driven (this session)** – I will dispatch a fresh sub‑agent for each task, review between tasks, and iterate quickly.
2. **Parallel Session** – Open a new session in a worktree and run the `superpowers:executing-plans` skill to batch‑execute the plan.

Which approach would you like to take?