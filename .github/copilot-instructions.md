# Copilot Instructions for OFX

**Note:** The documentation in this repository is intended for end users only. There is no developer or internal guide included or distributed. All documentation updates should focus on end-user guidance, not internal or developer-facing details.

## Project Overview

OFX (Offensive Flow Executor) is a red team automation toolkit providing:
- Workflow execution engine with matrix strategies
- Post-exploitation runners (SSH, WebShell, WinRM, SMBExec, WMIExec)
- Webshell generators and clients
- Enumeration tool integrations

**Python Version:** 3.12+ (downgraded from 3.14 for Debian compatibility)

## Architecture

### Runner Module (Workflow Execution)

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

### Post-Exploitation Module (Extendable Architecture)

The post module ([src/ofx/api/post/](../src/ofx/api/post/)) uses an **extendable runner pattern**:

- **Base class** ([src/ofx/api/post/base.py](../src/ofx/api/post/base.py)):
  - `PostRunnerBase`: Abstract base class with `run()`, `upload()`, `download()`, `interactive_shell()` methods
  - `CommandRunner`: Protocol for duck-typing compatibility
- **Registry** ([src/ofx/api/post/registry.py](../src/ofx/api/post/registry.py)):
  - `RunnerRegistry`: Dynamic runner discovery and factory creation
  - Use `@RunnerRegistry.register("name")` decorator to add new runners
- **Runners** ([src/ofx/api/post/runners/](../src/ofx/api/post/runners/)):
  - `PostSSH`: SSH command execution with SCP file transfers, ControlMaster, password auth (sshpass), opsec mode (command-to-file), retries with backoff, command logging, proxy/jump host support
  - `PostWebShell`: Wrapper around `WebShellClient`
  - `PostWinRM`: PowerShell/CMD execution with base64 file transfers, SSL support, retries, AMSI bypass, opsec mode, chunked upload for large files
  - `PostSMBExec`: SMB-based execution via impacket
  - `PostWMIExec`: WMI-based execution via impacket

**Import convention**: 
```python
from ofx.api.post import RunnerRegistry, PostSSH, PostWebShell
runner = RunnerRegistry.create("ssh", host="192.168.1.100", user="root")
```

### Cloud Module (VPS Integration)

The cloud module ([src/ofx/cloud/](../src/ofx/cloud/)) provides cloud VPS lifecycle management and distributed execution:

- **Base & Registry** ([src/ofx/cloud/base.py](../src/ofx/cloud/base.py)):
  - `CloudProvider`: Abstract base class with async `create_instance()`, `wait_until_ready()`, `destroy_instance()`, `get_instance()`, snapshot methods
  - `CloudProviderRegistry`: Decorator-based registration (`@CloudProviderRegistry.register("name")`)
- **Providers** ([src/ofx/cloud/providers/](../src/ofx/cloud/providers/)):
  - `DigitalOceanProvider`: Droplet lifecycle via pydo (optional dep)
  - `AWSProvider`: EC2 instance lifecycle via boto3 (optional dep)
  - `StaticProvider`: Pre-existing VPS wrapper (no provisioning/teardown)
- **Fleet** ([src/ofx/cloud/fleet_input.py](../src/ofx/cloud/fleet_input.py), [src/ofx/cloud/fleet_distributor.py](../src/ofx/cloud/fleet_distributor.py)):
  - `FleetInputParser`: Parses IPs, CIDRs, IP ranges, hostnames, files with deduplication and exclusion
  - `FleetDistributor`: chunk/round-robin/subnet/line distribution across fleet instances
  - `expand_fleet_to_matrix()`: Bridge between fleet config and MatrixJobRunner
- **Config** ([src/ofx/cloud/config.py](../src/ofx/cloud/config.py)):
  - `CloudProfileManager`: Named profiles stored in `~/.ofx/cloud.yml` with resolve/merge logic
- **Models** ([src/ofx/models/cloud.py](../src/ofx/models/cloud.py)):
  - `CloudConfig`: Full cloud configuration (provider, region, size, image, SSH/WinRM settings, opsec, lifecycle)
  - `FleetStrategy` in [src/ofx/models/strategy.py](../src/ofx/models/strategy.py): count, input, distribution mode
  - Job `cloud` field accepts string (profile name), dict, or `CloudConfig`
- **CloudJobRunner** ([src/ofx/runner/execution/cloud_job.py](../src/ofx/runner/execution/cloud_job.py)):
  - Extends `BaseRunner[Job]`, provisions VPS in `_pre_run`, runs steps remotely via PostSSH/PostWinRM in `_do_run`, destroys in `_post_run`
  - `CloudStepRunner`: Executes individual steps on the remote host
  - Auto-integrated in `WorkflowExecutionManager._build_stage_runners()` when `job.cloud` is set
- **CLI** ([src/ofx/commands/cloud/](../src/ofx/commands/cloud/)): `ofx cloud profile|instance|image|fleet|test|providers` subcommands
- **Sessions** ([src/ofx/cloud/sessions/](../src/ofx/cloud/sessions/)): Detached fire-and-forget execution with lifecycle management
  - `SessionManager`: Submit, status, fetch, cancel, destroy for local and cloud sessions
  - `SessionStore`: JSON file persistence with `fcntl` file locking under `~/.ofx/sessions/<id>/`
  - `build_session_script()`: Generates self-contained bash/PowerShell scripts from job steps
  - **At-rest encryption**: Per-session random AES-256 key; output encrypted with `openssl enc -aes-256-cbc -pbkdf2 -iter 100000` on Linux, .NET AES on Windows; key file shredded after encryption; transparent decryption at fetch time
  - `encrypt_results()` / `decrypt_results()`: User-level Fernet passphrase encryption (optional second layer)
  - Session lifecycle: `provisioning → uploading → running → completed → fetched → encrypted → destroyed`

**Import convention**:
```python
from ofx.cloud import CloudProviderRegistry
provider = CloudProviderRegistry.create("digitalocean", token="...")
```

### Collections Module (Workflow Packaging)

The collections module ([src/ofx/collections/](../src/ofx/collections/)) manages installable workflow packages:

- **Manifest** ([src/ofx/collections/manifest.py](../src/ofx/collections/manifest.py)):
  - `CollectionManifest`: Pydantic model parsed from `collection.yaml` — name, version, description, author, license, min_ofx_version, workflows, tools, dependencies, tags
  - `InstalledCollection`: Metadata for installed collections stored in `installed.json`
  - `CollectionIndex` / `CollectionIndexEntry`: Remote community index models with `.search()` method
  - `from_directory()`: Auto-discovers `.yml`/`.yaml` workflow files when manifest omits them
- **Manager** ([src/ofx/collections/manager.py](../src/ofx/collections/manager.py)):
  - `CollectionManager`: Full lifecycle — `add()`, `remove()`, `update()`, `list_installed()`, `get()`, `info()`, `collection_workflow_dirs()`, `migrate_from_assets()`
  - `DEFAULT_COLLECTION_ORG = "https://github.com/ofx-workflows"` — bare names resolve here
  - `resolve_source()`: bare name → `ofx-workflows/<name>`, `org/repo` → `github.com/org/repo`, full URL → passthrough
  - Recursive dependency resolution in `add(install_deps=True)` — installs `dependencies` from manifest
  - Lightweight semver: `check_version_constraint()` supports `>=`, `>`, `<=`, `<`, `==`, `!=`, `~=`
  - `min_ofx_version` gate warns when OFX version is below requirement
  - Storage: `~/.ofx/collections/installed.json` registry + `~/.ofx/collections/<name>/` directories
- **Index Client** ([src/ofx/collections/index.py](../src/ofx/collections/index.py)):
  - `IndexClient`: Fetches/caches index from `https://raw.githubusercontent.com/ofx-workflows/index/main/index.json` with 1-hour TTL
  - `search()`, `get_entry()` for community collection discovery
- **CLI** ([src/ofx/commands/flow/collection.py](../src/ofx/commands/flow/collection.py)):
  - `ofx flow collection add|remove|update|list|info|search|migrate` subcommands
  - `add --no-deps` to skip dependency resolution
- **Workflow search integration**: `get_workflow_search_dirs()` in settings.py automatically includes all installed collection directories in the workflow search path

**Import convention**:
```python
from ofx.collections import CollectionManager, CollectionManifest
mgr = CollectionManager()
mgr.add("recon-tools")  # installs from ofx-workflows org
```

## Workflows & Models

- Workflows: YAML parsed via `Workflow` model ([src/ofx/models/workflow.py](../src/ofx/models/workflow.py)); job IDs must match `[A-Za-z0-9_-]+`, `needs` validated, and steps get `step_index` assigned during validation.
- Steps: must define exactly one of `run`, `script`, `script_file`, or `uses` ([src/ofx/models/step.py](../src/ofx/models/step.py)); `interactive` only honored when a stage has a single job, otherwise it is ignored.
- Matrix strategy: jobs with `strategy.matrix` expand into multiple instances with cartesian product of matrix values; supports `max_parallel`, `fail_fast`, `include`, `exclude`; matrix values accessible via `{{ matrix.key }}` context ([src/ofx/models/job.py](../src/ofx/models/job.py), [src/ofx/utils/matrix.py](../src/ofx/utils/matrix.py)).
- Cloud jobs: jobs with `cloud` field are routed to `CloudJobRunner` which provisions VPS, runs steps remotely via PostSSH/PostWinRM, and destroys on completion; cloud config accepts string (profile name), dict, or `CloudConfig` model ([src/ofx/models/cloud.py](../src/ofx/models/cloud.py)).
- Fleet strategy: `strategy.fleet` distributes targets across multiple VPS; supports chunk/round-robin/subnet/line distribution; input parsing handles IPs, CIDRs, ranges, hostnames, files ([src/ofx/models/strategy.py](../src/ofx/models/strategy.py)).
- Reusable workflows: steps with `uses` create a nested `WorkflowRunner`, inheriting envs and optionally secrets (`secrets: inherit`) while respecting workflow search paths ([src/ofx/runner/execution/step.py](../src/ofx/runner/execution/step.py)).

## Execution & Context

- Workflow discovery: `find_workflow` searches current dir, `~/.ofx/workflows`, installed collection directories, then remote URL or git repo clones; `get_workflow_search_dirs()` lazily aggregates all search paths including `~/.ofx/collections/*/`; file extensions `.yml/.yaml` only ([src/ofx/utils/workflow_utils.py](../src/ofx/utils/workflow_utils.py), [src/ofx/settings.py](../src/ofx/settings.py)).
- Execution plan: dependencies topologically sorted into parallel stages via `find_parallel_schedule`; jobs in the same stage run concurrently; matrix jobs expanded before scheduling ([src/ofx/runner/execution/workflow.py](../src/ofx/runner/execution/workflow.py)).
- Run contexts: `RunContext` merges env vars with PATH prepended by `~/Tools/bin` and sets `UV_TOOL_BIN_DIR`; matrix context available as `ctx.vars['matrix']` during job execution ([src/ofx/runner/core/models.py](../src/ofx/runner/core/models.py) and [src/ofx/utils/env.py](../src/ofx/utils/env.py)).
- Registry: runners use namespaced keys and `RunnerRegistryKeys` constants; supports memory, file, Redis, etcd, and memcached backends; provides data access in templates via `jobs` and `steps` variables ([src/ofx/runner/registry/](../src/ofx/runner/registry/)).
- Templates: all string/number/bool fields pass through async Jinja using `{{ ... }}` delimiters; helper funcs include `sudo`, `tools_dir/tools_bin_dir`, `uv_install/go_install/cargo_install/npm_install/static_install`, `file_read/file_write`, `file_exists`, and `env`; matrix values accessible via `matrix` context; job and step results accessible via `jobs` (dict of job data) and `steps` (list of step data for current job) from registry ([src/ofx/runner/templates/](../src/ofx/runner/templates/)).
- Script channels: in Python scripts, use `publish(channel, data)`, `subscribe(channel)`, `wait_for(channel, condition, timeout=60)` for inter-job communication via workflow registry under "channels:{channel}" keys ([src/ofx/runner/commands/command.py](../src/ofx/runner/commands/command.py)). `subscribe` returns a generator that yields data when it changes, allowing auto-emit to subscribing clients.
- Defaults & working dirs: workflow/job/step shells and working directories cascade from `DefaultConfig` ([src/ofx/models/__init__.py](../src/ofx/models/__init__.py)); workflow default `workflows_base_dir` is appended to search paths.
 - Context precedence doc: [docs/guide/context-precedence.md](../docs/guide/context-precedence.md)

## Features & Behavior

- Tools block: `workflow.tools` installs binaries into `~/Tools/bin` via `ToolInstallerRunner`; can define `install`, optional `check`, and `post_install` commands ([src/ofx/runner/execution/tool_installer.py](../src/ofx/runner/execution/tool_installer.py)).
- Control flow: `run_if` on jobs/steps must resolve truthy or the runner marks them canceled; dependencies are rechecked at runtime; `failure()`/`always()` can run even when deps failed ([src/ofx/runner/execution/job.py](../src/ofx/runner/execution/job.py)).
- Outputs: stdout logged and optionally persisted to timestamped files under the run `output_path` when `log_stdout` is truthy ([src/ofx/runner/execution/step.py](../src/ofx/runner/execution/step.py)). Empty output directories are removed after workflow completion.
- Errors & retries: step retry logic with `retry`/`retry_delay` and minute-based `timeout`; job failures stop the stage unless `continue_on_error` is set on the step.

## CLI & Commands

- CLI entry: Typer app `ofx` registers `flow` (aliases `x`, `task`), `cloud`, `project`, `docs`, `doctor`, `secret`, `session` ([src/ofx/commands/__init__.py](../src/ofx/commands/__init__.py)).
- CLI commands: use `typing.Annotated` for all `typer.Option`/`typer.Argument` declarations; provide defaults inside `typer.Option` (strings default to `""`, bools to `False`) to avoid `NoneType.isidentifier` issues with Click/Typer.
- Running workflows: `ofx flow run <name> --input key=val --output <dir> --project <name>`; inputs are JSON-decoded when possible and shown via table; default output is a temp dir under `~/.ofx/tmp`; `--project` sets output to `<project>/logs` and injects project vars into context ([src/ofx/commands/flow/run.py](../src/ofx/commands/flow/run.py)).
- Collections: `ofx flow collection add|remove|update|list|info|search|migrate` manages workflow packages from the `ofx-workflows` GitHub org or custom git URLs ([src/ofx/commands/flow/collection.py](../src/ofx/commands/flow/collection.py)).
- Schema inspection: `ofx flow schema` shows workflow/job/step model schemas ([src/ofx/commands/dump.py](../src/ofx/commands/dump.py)).
- Validation & visualization: `ofx flow validate <name>` checks schema; `ofx flow visualize <name> --format dot|png|svg|pdf|mermaid|plantuml|d2|json|yaml` renders the DAG ([src/ofx/commands/flow/validate.py](../src/ofx/commands/flow/validate.py), [src/ofx/commands/flow/visualize.py](../src/ofx/commands/flow/visualize.py)).
- Secrets: CLI loads secrets from `~/.ofx/secrets` and falls back to `secrets.enc`; `secrets: inherit` passes parent secrets into reusable workflows ([src/ofx/utils/secrets.py](../src/ofx/utils/secrets.py)).
- Progress UX: workflow/job runners use `rich` progress bars; interactive steps suppress nested progress to keep TTY usable.

## Development

### Testing
- Use `uv run --extra test pytest` for unit/integration tests
- YAML flow fixtures live in [tests/flows](../tests/flows) and cover hooks, parallelism, and tool installs

### Documentation
- MkDocs sources in [docs](../docs)
- Build with `make docs` or `uv run --extra docs mkdocs build --clean --strict -f mkdocs.yml -d src/ofx/data/site`
- Serve via `uv run ofx docs serve` after build

### Packaging & Distribution

Multi-platform distribution via Docker:

```bash
# Build all packages (deb, rpm, wheel)
make packages

# Build for AMD64 + ARM64
make packages-multiarch

# Build Windows executable
make pkg-windows

# Bump version across all files
make version V=0.4.0
```

**Package files:**
- `debian/` - Debian package configuration
- `packaging/rpm/ofx.spec` - RPM spec for Fedora/RHEL
- `packaging/winget/redteam.OFX.yaml` - Windows Package Manager manifest
- `packaging/windows/build-exe.py` - PyInstaller build script
- `Dockerfile.pkg` - Multi-stage Docker builder

### CI/CD

GitHub Actions workflows (using absolute URLs for Gitea runner compatibility):
- `.github/workflows/release.yml` - Build packages and create releases
- `.github/workflows/publish.yml` - Publish to PyPI/Gitea registry
- `.github/workflows/tests.yml` - Run tests

### Style Guide
- Ruff enforces linting rules (line length via black), Python 3.12
- Async-first execution, so keep new runners/commands async-aware
- Propagate `RunContext` consistently
- Use absolute GitHub URLs in workflow files for Gitea compatibility: `https://github.com/actions/checkout@v4`
