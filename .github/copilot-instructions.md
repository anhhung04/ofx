# Copilot Instructions for OFX
**Note:** The documentation in this repository is intended for end users only. There is no developer or internal guide included or distributed. All documentation updates should focus on end-user guidance, not internal or developer-facing details.

## Runner Architecture (Modular Structure)

The runner module uses a **modular architecture** organized into specialized subdirectories:

- **Core components** ([src/ofx/runner/core/](../src/ofx/runner/core/)): Base runner class and data models
  - `BaseRunner`: Abstract base class for all runners with lifecycle hooks (_pre_run, _do_run, _post_run)
  - `RunContext`, `RunnerStatus`, `RunResult`, `RunType`: Core data models for execution state
- **Execution** ([src/ofx/runner/execution/](../src/ofx/runner/execution/)): Workflow/job/step runners and orchestration
  - `WorkflowRunner`: Orchestrates parallel job execution with dependency resolution
  - `JobRunner`: Executes individual jobs with step sequencing
  - `StepRunner`: Runs steps with retry logic and hooks
  - `WorkflowExecutionManager`: Executes staged jobs and aggregates errors
  - `WorkflowScheduler`: Builds the parallel schedule
  - `ExecutionSummaryReporter`: Produces summary and unified summary objects
- **Commands** ([src/ofx/runner/commands/](../src/ofx/runner/commands/)): Command/script execution
  - `CommandRunner`, `ScriptRunner`
  - `CommandExecutor`: Subprocess handling and output decoding
- **Context** ([src/ofx/runner/context/](../src/ofx/runner/context/)): RunContext merging helpers
  - `RunnerContextBuilder`: Merges env/inputs/secrets/vars with copy-on-write
- **Registry** ([src/ofx/runner/registry/](../src/ofx/runner/registry/)): Registry adapters and factory
  - `RegistryAdapter`, `RegistryFactory`, `MemoryJobRegistry`, `FileJobRegistry`, etc.
- **Matrix** ([src/ofx/utils/matrix.py](../src/ofx/utils/matrix.py)): Matrix strategy expansion
  - `expand_jobs`, `process_matrix_value`, etc.: Generate job variations from matrix configurations with include/exclude rules
- **Templates** ([src/ofx/runner/templates/](../src/ofx/runner/templates/)): Jinja2 template resolution
  - `TemplateResolver`: Async template resolution with caching and registry-based data access
  - `TemplateHelpers`: Helper functions for templates (sudo, uv_install, file_read, etc.)

**Import convention**: Use public API `from ofx.runner import WorkflowRunner, RunContext, ...` or explicit paths `from ofx.runner.execution import WorkflowRunner`, `from ofx.runner.commands import CommandRunner`.

## Workflows & Models

- Workflows: YAML parsed via `Workflow` model ([src/ofx/models/workflow.py](../src/ofx/models/workflow.py)); job IDs must match `[A-Za-z0-9_-]+`, `needs` validated, and steps get `step_index` assigned during validation.
- Steps: must define exactly one of `run`, `script`, `script_file`, or `uses` ([src/ofx/models/step.py](../src/ofx/models/step.py)); `interactive` only honored when a stage has a single job, otherwise it is ignored.
- Matrix strategy: jobs with `strategy.matrix` expand into multiple instances with cartesian product of matrix values; supports `max_parallel`, `fail_fast`, `include`, `exclude`; matrix values accessible via `${{ matrix.key }}` context ([src/ofx/models/job.py](../src/ofx/models/job.py), [src/ofx/utils/matrix.py](../src/ofx/utils/matrix.py)).
- Reusable workflows: steps with `uses` create a nested `WorkflowRunner`, inheriting envs and optionally secrets (`secrets: inherit`) while respecting workflow search paths ([src/ofx/runner/execution/step.py](../src/ofx/runner/execution/step.py)).

## Execution & Context

- Workflow discovery: `find_workflow` searches current dir, `~/.local/share/ofx/workflows`, then remote URL or git repo clones; file extensions `.yml/.yaml` only ([src/ofx/utils/workflow_utils.py](../src/ofx/utils/workflow_utils.py)).
- Execution plan: dependencies topologically sorted into parallel stages via `find_parallel_schedule`; jobs in the same stage run concurrently; matrix jobs expanded before scheduling ([src/ofx/runner/execution/workflow.py](../src/ofx/runner/execution/workflow.py)).
- Run contexts: `RunContext` merges env vars with PATH prepended by `~/Tools/bin` and sets `UV_TOOL_BIN_DIR`; matrix context available as `ctx.vars['matrix']` during job execution ([src/ofx/runner/core/models.py](../src/ofx/runner/core/models.py) and [src/ofx/utils/env.py](../src/ofx/utils/env.py)).
- Registry: runners use namespaced keys and `RunnerRegistryKeys` constants; supports memory, file, Redis, etcd, and memcached backends; provides data access in templates via `jobs` and `steps` variables ([src/ofx/runner/registry/](../src/ofx/runner/registry/)).
- Templates: all string/number/bool fields pass through async Jinja using `${{ ... }}` delimiters; helper funcs include `sudo`, `tools_dir/tools_bin_dir`, `uv_install/go_install/cargo_install/npm_install/static_install`, `file_read/file_write`, `file_exists`, and `env`; matrix values accessible via `matrix` context; job and step results accessible via `jobs` (dict of job data) and `steps` (list of step data for current job) from registry ([src/ofx/runner/templates/](../src/ofx/runner/templates/)).
- Defaults & working dirs: workflow/job/step shells and working directories cascade from `DefaultConfig` ([src/ofx/models/__init__.py](../src/ofx/models/__init__.py)); workflow default `workflows_base_dir` is appended to search paths.
 - Context precedence doc: [docs/guide/context-precedence.md](../docs/guide/context-precedence.md)

## Features & Behavior

- Tools block: `workflow.tools` installs binaries into `~/Tools/bin` via `ToolInstallerRunner`; can define `install`, optional `check`, and `post_install` commands ([src/ofx/runner/execution/tool_installer.py](../src/ofx/runner/execution/tool_installer.py)).
- Hooks: steps support `before_step`, `after_step`, `on_retry`, `on_skip`, and `on_timeout` scripts executed with the configured shell; workflow/job hooks exist in models but only step hooks have concrete runner support.
- Control flow: `run_if` on jobs/steps must resolve truthy or the runner marks them canceled; dependencies are rechecked at runtime; `failure()`/`always()` can run even when deps failed ([src/ofx/runner/execution/job.py](../src/ofx/runner/execution/job.py)).
- Outputs: stdout logged and optionally persisted to timestamped files under the run `output_path` when `log_stdout` is truthy ([src/ofx/runner/execution/step.py](../src/ofx/runner/execution/step.py)). Empty output directories are removed after workflow completion.
- Errors & retries: step retry logic with `retry`/`retry_delay` and minute-based `timeout`; job failures stop the stage unless `continue_on_error` is set on the step.

## CLI & Commands

- CLI entry: Typer app `ofx` registers `flow` (aliases `x`, `task`), `dump`, `asset`, `project`, `docs`, `doctor`, `secret` ([src/ofx/commands/__init__.py](../src/ofx/commands/__init__.py)).
- CLI commands: use `typing.Annotated` for all `typer.Option`/`typer.Argument` declarations; provide defaults inside `typer.Option` (strings default to `""`, bools to `False`) to avoid `NoneType.isidentifier` issues with Click/Typer.
- Running workflows: `ofx flow run <name> --input key=val --output <dir>`; inputs are JSON-decoded when possible and shown via table; default output is a temp dir under `/tmp/.ofx` ([src/ofx/commands/flow/run.py](../src/ofx/commands/flow/run.py)).
- Validation & visualization: `ofx flow validate <name>` checks schema; `ofx flow visualize <name> --format dot|png|svg|pdf|mermaid|plantuml|d2|json|yaml` renders the DAG ([src/ofx/commands/flow/validate.py](../src/ofx/commands/flow/validate.py), [src/ofx/commands/flow/visualize.py](../src/ofx/commands/flow/visualize.py)).
- Secrets: CLI loads secrets from `~/.local/share/ofx/secrets` and falls back to `secrets.enc`; `secrets: inherit` passes parent secrets into reusable workflows ([src/ofx/utils/secrets.py](../src/ofx/utils/secrets.py)).
- Progress UX: workflow/job runners use `rich` progress bars; interactive steps suppress nested progress to keep TTY usable.

## Development

- Testing: prefer `uv run --extra test pytest` for unit/integration tests; YAML flow fixtures live in [tests/flows](../tests/flows) and cover hooks, parallelism, and tool installs.
- Docs: mkdocs sources in [docs](../docs); build with `uv run --extra docs mkdocs build --clean --strict -f mkdocs.yml -d src/ofx/data/site` or `make docs`. Serve via `uv run ofx docs serve` after build output exists.
- Packaging & deps: `uv sync` installs dependencies (`uv sync --extra test` adds test deps); CLI entry point is `ofx=ofx:main` set in [pyproject.toml](../pyproject.toml).
- Style: Ruff enforces linting rules (line length via black), Python 3.12; async-first execution, so keep new runners/commands async-aware and propagate `RunContext` consistently.
