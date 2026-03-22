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

## Quick Start

```bash
# Run a workflow (example)
uv run ofx flow run path/to/workflow.yml
```

## Environment / Profiles

- Cloud profiles are stored in `~/.ofx/cloud.yml`.
- Useful env var: `OFX_DEBUG=1` enables full tracebacks.
- Set `OFX_DEBUG=1` when debugging.

## Gotchas & Non‑Obvious Patterns

- Cloud fleet requires the `fleet` section in the matrix strategy; ensure SSH keys are reachable.
- Opsec mode disables command echoing; use `opsec: true` in `CloudConfig` when needed.
- Remote steps need a compatible Python interpreter; `CloudStepRunner` probes `python3` then `python`.

## Testing Notes

- Tests reside in `tests/`.
- Run all tests: `uv run pytest`
- Run a single test file: `uv run pytest tests/test_flowrun.py`
- Run with coverage (already listed above).

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
- `Job` — `needs` (list of job IDs), `strategy` (matrix), `steps`, `cloud` (optional `CloudConfig | str`)
- `Step` — exactly one run type must be present: `run` (shell command), `script` (inline Python), `script_file`, `uses` (reusable workflow), or `task` (pre-built security tool wrapper). Aliases used extensively (e.g. `if`, `continue-on-error`, `retry-delay`).
- `CloudConfig` (`models/cloud.py`) — cloud VPS configuration. Can be a string (profile slug from `~/.ofx/cloud.yml`) or an inline object. Supports `provider` (static/digitalocean/aws), SSH/WinRM connection settings, opsec mode, auto-destroy lifecycle.
- `CloudHostEntry` — single host entry for static fleet usage (host, ssh_user, ssh_port, ssh_key).
- `MatrixStrategy` (`models/strategy.py`) — matrix variables, max_parallel, fail_fast, include/exclude, optional `fleet` for cloud distribution.
- `FleetStrategy` — fleet distribution: count, input (IPs/CIDRs/files), distribution mode (chunk/round-robin/subnet/line), expand_cidrs, exclude.

### Runner (`src/ofx/runner/`)
- `api.py:run_workflow()` — public async entry point; resolves the workflow file, builds `RunContext`, instantiates `WorkflowRunner`
- `core/base.py:BaseRunner` — generic `TModel`-typed base; drives the state machine (`IDLE → RUNNING → FINISHED → COMPLETED/FAILED`), handles durable checkpoints, delegates to `_pre_run()/_run()/_post_run()`
- `execution/workflow.py:WorkflowRunner` — resolves templates, dispatches jobs via `WorkflowScheduler`; calls sub-runners for `JobRunner` / `MatrixJobRunner`
- `execution/job.py` / `execution/step.py` — job and step runners
- `execution/cloud_job.py` — `CloudJobRunner` and `CloudStepRunner` for remote VPS execution
- `execution/workflow_scheduler.py` — topological sort; runs independent jobs in parallel via `asyncio`
- `execution/workflow_execution.py` — `WorkflowExecutionManager` dispatches to `CloudJobRunner` / `MatrixJobRunner` / `JobRunner` based on job config
- `context/` — `RunContext` (inputs, secrets, envs, vars, output_path) + `RunnerContextBuilder` (immutable copy-on-update pattern)
- `templates/` — Jinja2 `TemplateResolver`; built-in API functions are injected into the template environment
- `registry/` — pluggable job-output registry (memory / file / Redis / Memcached / etcd). `RegistryFactory` picks the backend from `settings.registry_backend`. A `CachedRegistryAdapter` wraps every backend; a `FailoverRegistryAdapter` falls back to memory on errors.
- `channels.py` — file-based inter-step communication (`channel_send` / `channel_recv` in templates)

### Cloud execution (`src/ofx/cloud/`)
- `base.py` — abstract `CloudProvider` with `CloudProviderRegistry` (decorator-based registration)
- `providers/static.py` — wraps pre-existing hosts; supports single host and multi-host fleet (`create_fleet_instances()`)
- `providers/aws.py` — EC2 via boto3; launch params, user data, AMI snapshots
- `providers/digitalocean.py` — droplets via pydo; SSH key lookup, VPC, tags, snapshots
- `config.py` — `CloudProfileManager` persists profiles to `~/.ofx/cloud.yml`; `resolve()` merges profile base + inline overrides
- `ssh.py` — `wait_for_connectivity()` helper for SSH/WinRM readiness
- `fleet_input.py` — `FleetInputParser` parses IPs, CIDRs, ranges, hostnames, files; expands/deduplicates/excludes
- `fleet_distributor.py` — `FleetDistributor` splits targets across N instances; `expand_fleet_to_matrix()` bridges fleet config to matrix combinations

### Cloud job runner (`src/ofx/runner/execution/cloud_job.py`)
- `CloudJobRunner(BaseRunner[Job])` — provisions VPS via cloud provider, runs steps via `CloudStepRunner`, downloads outputs, destroys VPS on completion
- `CloudMatrixJobRunner(BaseRunner[Job])` — meta-runner for cloud+matrix and/or cloud+fleet jobs. Expands matrix combinations × fleet target chunks (Cartesian product), then spawns a separate `CloudJobRunner` per combination. Each CloudJobRunner provisions its own VPS. Fleet chunk files are uploaded to each VPS as `$FLEET_INPUT_FILE`. Parallelism controlled by `strategy.max_parallel`. Chunk files cleaned up after all combinations complete.
- `CloudStepRunner(BaseRunner)` — executes steps remotely via `PostSSH`/`PostWinRM`:
  - `run:` — shell commands sent directly
  - `script:` — inline Python bundled with `ofx.api` deps via `build_bundle()`, uploaded and executed with discovered `python3`
  - `script_file:` — same bundle mechanism for file-based Python scripts
  - `task:` — command built locally via `Task.build_command()`, executed remotely; stdout parsed for typed outputs
  - Python discovery: probes `python3`, `python`, and common absolute paths on the remote host (cached per runner)
- Output streaming: `CloudStepRunner._post_run()` logs stdout to the local console and saves `StepExecutionResult` to registry, matching local step runner behavior
- State machine: fully compliant with `BaseRunner` lifecycle (IDLE → RUNNING → FINISHED → COMPLETED/FAILED) with durable checkpoints

### Multi-cloud support
Multiple jobs in the same workflow can each have different `cloud:` configs (different providers, profiles, regions). `WorkflowExecutionManager._build_stage_runners()` creates independent runner instances per job: `CloudJobRunner` for single-VPS jobs, `CloudMatrixJobRunner` for matrix/fleet expansion. Jobs in the same dependency stage run in parallel via `asyncio`. Each runner provisions/destroys its own VPS.

Example multi-cloud workflow:
```yaml
jobs:
  recon:
    cloud: do-nyc      # DigitalOcean profile
    steps:
      - run: nmap ...
  exploit:
    cloud:
      provider: aws
      region: us-east-1
      size: t3.medium
    needs: [recon]
    steps:
      - run: ...
  local-job:            # No cloud field — runs locally
    needs: [exploit]
    steps:
      - run: echo "done"
```

### Sessions (`src/ofx/cloud/sessions/`)
Detached job execution (fire-and-forget) with status polling and result retrieval.
- `SessionManager` — submit/status/logs/fetch/cancel/destroy lifecycle
- `SessionStore` — JSON persistence in `~/.ofx/sessions/{session_id}/session.json`
- Supports LOCAL (background subprocess) and CLOUD (provisioned VPS via SSH/WinRM)
- At-rest encryption via openssl (AES-256-CBC + PBKDF2); user-level encryption on fetch
- Status markers: `__OFX_DONE__` / `__OFX_FAIL__` in log tail

CLI:
```bash
ofx session submit workflow.yml --cloud profile-name
ofx session list
ofx session status <id>
ofx session logs <id> --tail 100
ofx session fetch <id> --passphrase secret
ofx session cancel <id>
ofx session destroy <id>
ofx session clean --older-than 7d
```

### Post-exploitation runners (`src/ofx/api/post/`)
- `base.py` — `PostRunnerBase` (ABC) with `run()`, `upload()`, `download()`, `detect_os()`, `is_root()`
- `registry.py` — `RunnerRegistry` with `@register()` decorator
- `runners/ssh.py` — `PostSSH` with ControlMaster, opsec mode, retry logic, command logging
- `runners/winrm.py` — `PostWinRM` for Windows targets
- `runners/smbexec.py`, `wmiexec.py`, `webshell.py` — additional execution backends
- Used by `CloudJobRunner._create_remote_runner()` and `SessionManager._reconnect()`

### Settings (`src/ofx/settings.py`)
`Settings` (pydantic-settings) reads from env vars prefixed `OFX_`. Key paths:
- `~/.ofx/` — all runtime data (workflows, projects, collections, secrets, registry)
- `~/.ofx/cloud.yml` — cloud provider profiles
- `~/.ofx/sessions/` — session data and results
- `~/.ofx/workflow_schema.json` — exported JSON schema for YAML language server
- `OFX_DEBUG=1` — enables full tracebacks and debug logging

### Collections (`src/ofx/collections/`)
`CollectionManager` installs workflow collections into `~/.ofx/collections/`. Installed collection directories are auto-appended to the workflow search path at runtime via `get_workflow_search_dirs()`.

### Built-in APIs (`src/ofx/api/`)
~96 modules (recon, exploitation, post-exploitation, etc.) injected as helpers into the Jinja2 template context. All are accessible in `run:` fields as `{{ api_function(...) }}`.

### API bundle system (`src/ofx/api/bundle/`)
- `analyzer.py` — detects `ofx.api` imports in user scripts
- `collector.py` — collects required module source files
- `builder.py` — `build_bundle()` creates a self-extracting Python bootstrap (base64-encoded zip + script) that can run on remote hosts without `ofx` installed
- Used by `CloudStepRunner` for `script:` and `script_file:` step types

### Task system (`src/ofx/tasks/`)
Pre-built security tool wrappers with structured output parsing, inspired by secator.
- `base.py` — abstract `Task` class; declares CLI option mapping (`opts`), `extra_flags`, `build_command()`, `parse_output()`, install/health-check logic. Uses `__init_subclass__` to isolate mutable class attrs per-subclass.
- `output_types.py` — 10 Pydantic models for structured results: `Port`, `Url`, `Vulnerability`, `Subdomain`, `Ip`, `Tag`, `Record`, `Domain`, `Certificate`, `Exploit`. Each has `_type` discriminator, `_uuid` dedup hash, `to_dict()` serialization.
- `registry.py` — `TaskRegistry` with `@register()` decorator; auto-discovers modules under `ofx.tasks.tools/` on first access (thread-safe double-checked locking).
- `tools/` — 10 tool wrappers: nmap, naabu, httpx, ffuf, feroxbuster, katana, subfinder, dnsx, nuclei, wafw00f.
- `TaskRunner` (`src/ofx/runner/tasks/runner.py`) — `BaseRunner[TaskExecution]` that builds the command, executes via `CommandExecutor`, parses output into typed objects, deduplicates via `_uuid`, and stores `typed_outputs` alongside regular outputs in the registry.
- Template helpers: `ports()`, `urls()`, `vulns()`, `subdomains()`, `ips()`, `tags()`, `records()`, `domains()`, `of_type()` for filtering typed outputs in Jinja2 templates.
- CLI: `ofx flow tasks list [-c category/]` and `ofx flow tasks info <name>`.

## Key conventions

- **Workflow YAML files** start with `# yaml-language-server: $schema=<path>` for IDE support. Generate the schema with `ofx flow schema schema` (writes to `~/.ofx/workflow_schema.json`). Create a new workflow scaffold with `ofx flow init <name>`.
- **Aliases**: YAML fields use kebab-case aliases (`continue-on-error`, `retry-delay`, `working-directory`); the Python attrs use underscores. Always use `model_validate()` / YAML load, not direct construction.
- **Async**: runner code is async throughout. Sync callers use `asyncio.run()`.
- **Tests**: `conftest.py` auto-patches Redis/Memcached with in-memory fakes. Integration tests that actually run workflows are in `test_flowrun.py`; test workflow YAMLs live in `tests/flows/`.
- **Cloud config**: can be a string (profile slug) or an inline `CloudConfig` dict. The `parse_cloud_field()` normalizer handles both. Profiles are managed via `ofx cloud profile add/list/show/remove/default`.
- **Cloud fleet**: `FleetStrategy` in `MatrixStrategy.fleet` defines target distribution. `expand_fleet_to_matrix()` converts fleet config to matrix combinations. `CloudMatrixJobRunner` handles cloud+fleet expansion.
- **Cloud + matrix/fleet**: When a job has both `cloud:` and `strategy.matrix` or `strategy.fleet`, `WorkflowExecutionManager` dispatches to `CloudMatrixJobRunner`. This meta-runner expands combinations (matrix × fleet Cartesian product) and spawns a separate `CloudJobRunner` per combination, each provisioning its own VPS. Fleet chunk files are uploaded to each VPS and exposed as `$FLEET_INPUT_FILE`. Parallelism is controlled by `strategy.max_parallel`.
- **Task steps**: Use `task: <name>` + `with:` to invoke a registered tool wrapper. The `with:` dict must include `target` (or `targets`) plus tool-specific options. Output is parsed into typed objects stored in `outputs.typed_outputs`. Template helpers (`ports()`, `urls()`, `vulns()`, etc.) filter typed outputs by `_type`. New tools: subclass `Task`, set `opts`/`extra_flags`/`output_types`, implement `parse_output()`, register with `@TaskRegistry.register("name")`.

## Known gaps / future work

- **Cloud fleet result tracking**: Aggregating results from fleet runs across multiple VPS instances into a unified view.
