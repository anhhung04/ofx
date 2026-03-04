# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands use `uv run` as the package manager.

```bash
# Run the CLI
uv run ofx <command>

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_flowrun.py

# Run a single test by name
uv run pytest tests/test_flowrun.py::test_name -v

# Lint
uv run ruff check src/

# Format / auto-fix
uv run ruff check --fix src/
uv run ruff format src/

# Type check
uv run mypy src/

# Run tests with coverage
uv run pytest --cov=src/ofx --cov-report=term-missing
```

## Architecture

OFX is a YAML-based workflow runner. The execution path is:

**CLI → models (Pydantic) → runner → registry**

### Entry point
`src/ofx/__init__.py` → `src/ofx/commands/__init__.py:main()` registers all sub-apps via `add_app()` and calls `typer`.

### Command modules (`src/ofx/commands/`)
Each sub-app (flow, project, cloud, session, secret, docs) exposes `app`, `NAME`, `HELP`, and optionally `ALIAS`. Heavy logic lives in handler classes imported lazily inside the command functions. New commands follow this pattern: a thin `@app.command()` in `app.py` that delegates to a `FooHandler` class in a separate file.

### Models (`src/ofx/models/`)
Pydantic v2 models define the YAML schema:
- `Workflow` — top-level; validates job IDs, dependency graph (cycle detection), populates `jid`/`step_index`/`name`
- `Job` — `needs` (list of job IDs), `strategy` (matrix), `steps`
- `Step` — exactly one run type must be present: `run` (shell command), `script` (inline Python), `script_file`, or `uses` (reusable workflow). Aliases used extensively (e.g. `if`, `continue-on-error`, `retry-delay`).

### Runner (`src/ofx/runner/`)
- `api.py:run_workflow()` — public async entry point; resolves the workflow file, builds `RunContext`, instantiates `WorkflowRunner`
- `core/base.py:BaseRunner` — generic `TModel`-typed base; drives the state machine (`IDLE → RUNNING → FINISHED → COMPLETED/FAILED`), handles durable checkpoints, delegates to `_pre_run()/_run()/_post_run()`
- `execution/workflow.py:WorkflowRunner` — resolves templates, dispatches jobs via `WorkflowScheduler`; calls sub-runners for `JobRunner` / `MatrixJobRunner`
- `execution/job.py` / `execution/step.py` — job and step runners
- `execution/workflow_scheduler.py` — topological sort; runs independent jobs in parallel via `asyncio`
- `context/` — `RunContext` (inputs, secrets, envs, vars, output_path) + `RunnerContextBuilder` (immutable copy-on-update pattern)
- `templates/` — Jinja2 `TemplateResolver`; built-in API functions are injected into the template environment
- `registry/` — pluggable job-output registry (memory / file / Redis / Memcached / etcd). `RegistryFactory` picks the backend from `settings.registry_backend`. A `CachedRegistryAdapter` wraps every backend; a `FailoverRegistryAdapter` falls back to memory on errors.
- `channels.py` — file-based inter-step communication (`channel_send` / `channel_recv` in templates)

### Settings (`src/ofx/settings.py`)
`Settings` (pydantic-settings) reads from env vars prefixed `OFX_`. Key paths:
- `~/.ofx/` — all runtime data (workflows, projects, collections, secrets, registry)
- `~/.ofx/workflow_schema.json` — exported JSON schema for YAML language server
- `OFX_DEBUG=1` — enables full tracebacks and debug logging

### Collections (`src/ofx/collections/`)
`CollectionManager` installs workflow collections into `~/.ofx/collections/`. Installed collection directories are auto-appended to the workflow search path at runtime via `get_workflow_search_dirs()`.

### Built-in APIs (`src/ofx/api/`)
~96 modules (recon, exploitation, post-exploitation, etc.) injected as helpers into the Jinja2 template context. All are accessible in `run:` fields as `{{ api_function(...) }}`.

## Key conventions

- **Workflow YAML files** start with `# yaml-language-server: $schema=<path>` for IDE support. Generate the schema with `ofx flow schema schema` (writes to `~/.ofx/workflow_schema.json`). Create a new workflow scaffold with `ofx flow init <name>`.
- **Aliases**: YAML fields use kebab-case aliases (`continue-on-error`, `retry-delay`, `working-directory`); the Python attrs use underscores. Always use `model_validate()` / YAML load, not direct construction.
- **Async**: runner code is async throughout. Sync callers use `asyncio.run()`.
- **Tests**: `conftest.py` auto-patches Redis/Memcached with in-memory fakes. Integration tests that actually run workflows are in `test_flowrun.py`; test workflow YAMLs live in `tests/flows/`.
