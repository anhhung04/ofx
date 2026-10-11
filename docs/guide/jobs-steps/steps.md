# Steps

Steps are the smallest unit of execution in an OFX workflow. Each step runs a **module** — a built-in (shell/python) or user-defined function — a reusable workflow (`uses:`), or a data pipeline (`pipe:`), and can have its own environment and error handling.

---

## Step Syntax
```yaml
name: Example Workflow
jobs:
  example:
    name: Example Job
    steps:
      - name: Run Script
        module: shell
        with:
          cmd: ./myscript.sh
        env:
          VAR: value
        timeout: 10
        continue-on-error: true
```

---

## Step Fields
- `name`: (optional) Description of the step. **Must be unique within a job** — duplicate names cause a validation error.
- `module` / `uses` / `pipe`: **Exactly one** action per step
- `env`: (optional) Environment variables
- `timeout`: (optional) Max time in minutes (default: 1440). Supports Jinja2 expressions for dynamic scaling (see below).
- `retry`: (optional) Retry attempts on failure
- `retry_delay`: (optional) Seconds between retries (alias: `retry-delay`). Uses exponential backoff with jitter.
- `continue_on_error`: (optional) Continue even if this step fails (alias: `continue-on-error`). Outputs from the failed step are still accessible to later steps.
- `run_if`: (optional) Conditional execution (alias: `if`)
- `shell`: (optional) Shell used by `module: shell` steps (default: `/bin/bash`)
- `working_directory`: (optional) Execution directory (alias: `working-directory`)
- `log_stdout`: (optional) Save full stdout to `stdout_<job>_<step>.log` files (alias: `log-stdout`)
- `log_command`: (optional) Log the resolved command/script before executing (alias: `log-command`)
- `interactive`: (optional) Interactive mode (ignored for `uses`)
- `with`: (optional) Arguments for the module / inputs for `uses` (model field: `run_with`)
- `secrets`: (optional) Secrets for `uses` (`inherit` to pass parent secrets)

### Dynamic Timeout

The `timeout` field accepts Jinja2 template expressions, enabling timeout scaling based on inputs or matrix values:

```yaml
steps:
  - name: scan-targets
    module: shell
    with:
      cmd: nmap -iL {{ inputs.targets_file }}
    # Scale timeout: 15 min base + 1 min per 50 targets
    timeout: "{{ (inputs.target_count | int / 50) | int * 1 + 15 }}"
```

If the expression resolves to an invalid value, a default of 60 minutes is used with a warning.

---

## Advanced Usage
- Use `module: shell` + `with: {cmd: ...}` to run shell commands
- Use `module: python` + `with: {script: ...}` for inline Python code
- Use `module: python` + `with: {script_file: ...}` to execute an existing Python file (resolved relative to the workflow directory)
- Use `module: path/to/module.py::func` for user-defined Python modules (see [Modules](#modules) below)
- Use `uses:` to call a reusable workflow
- Use `pipe:` to declaratively transform data between steps (see [Pipe Steps](#pipe-steps) below)
- Use `if:` for conditional logic

---

## Pipe Steps

Pipe steps provide declarative ETL (Extract-Transform-Load) pipelines for processing data between steps without writing scripts. Use `pipe:` when you need to filter, map, sort, or format output from a previous step.

```yaml
steps:
  - module: modules/port_scan.py
    name: scan
    with:
      target: "{{ inputs.target }}"

  - name: http-targets
    pipe:
      input: "{{ steps.scan.outputs.typed_outputs | ports }}"
      filter: "state == 'open' and port in [80, 443, 8080]"
      map:
        url: "'http://' + host + ':' + str(port)"
        host: host
      sort: port
      unique: host
      format: lines
      field: url

  - name: screenshot
    module: shell
    with:
      cmd: gowitness file -f {{ steps.http-targets.outputs.file }}
```

### Pipe Configuration

| Field | Description |
|-------|-------------|
| `input` | **(required)** Jinja2 expression resolving to a list |
| `filter` | Python expression evaluated per item; item fields are local variables |
| `map` | Dict of `field: expression` — produces new objects with only mapped fields |
| `flatten` | Expand a nested list field in-place |
| `sort` | Sort by field name(s) (string or list) |
| `reverse` | Reverse the sort order (default: `false`) |
| `unique` | Deduplicate by field name(s) — first occurrence wins |
| `group-by` | Group items by a field value (output becomes dict of lists) |
| `offset` | Skip the first N items |
| `limit` | Keep at most N items |
| `format` | Output format: `json` (default), `jsonl`, `lines`, `csv`, `yaml` |
| `field` | For `lines` format, extract this field from each item |
| `separator` | Line separator for `lines` format (default: `\n`) |
| `headers` | Include header row in `csv` format (default: `true`) |

### Pipe Outputs

Access pipe results in subsequent steps:

- `{{ steps.<name>.outputs.items }}` — processed list (or dict if grouped)
- `{{ steps.<name>.outputs.count }}` — number of items
- `{{ steps.<name>.outputs.data }}` — formatted string
- `{{ steps.<name>.outputs.file }}` — path to temp file with formatted output

### ETL Template Helpers

These helpers work as both template functions and Jinja2 filters for inline transformations:

```yaml
# As filters (chainable):
module: shell
with:
  cmd: echo "{{ steps.scan.outputs.typed_outputs | ports | pluck('host') | unique_by('host') | to_lines }}"

# As functions:
module: shell
with:
  cmd: echo "{{ to_lines(pluck(ports(steps.scan.outputs.typed_outputs), 'host')) }}"
```

Available helpers: `pluck`, `to_lines`, `to_csv`, `to_jsonl`, `sort_by`, `unique_by`, `where`, `where_not`, `first`, `last`, `group_by`, `flatten`, `count_by`

---

## Modules

Modules are the execution primitives of a step. A step references exactly one module with `module:` and passes arguments via `with:`. Modules can be **built-in** (shell/python), **workflow-local** (a UDF file or a named module under `modules/`), or **remote** (published in a GitHub repo).

### Reference forms

Every accepted `module:` form:

| Reference | Meaning |
|-----------|---------|
| `shell`, `builtin.shell`, `local.builtin.shell` | Builtin `shell` module (all three are equivalent; `local.builtin.*` is the canonical form) |
| `python`, `builtin.python`, `local.builtin.python` | Builtin `python` module |
| `<file>.py`, `<file>.py::<func>` | Workflow-local UDF file (relative to the workflow directory, then the cwd); `<func>` defaults to `run` |
| `local.<name>` | Workflow-local module at `<workflow_dir>/modules/<name>.py` (function defaults to `run`) |
| `<owner>.<repo>.<module>` | Remote GitHub module: repo `github.com/<owner>/<repo>`, manifest entry `modules/<module>.py`, default branch |
| `<owner>.<repo>.<module>@<ref>` | Same, pinned to git tag/branch/commit `<ref>` |
| any namespaced form + `::<func>` | Non-default entry function |

Parsing order: `::` splits the function first, then `@` splits the ref; `.py`-suffixed specs are UDF files; `local.builtin.*`/`builtin.*`/bare names are builtins; `local.*` is a workflow-local module; three-or-more dotted segments are remote.

### Built-in modules

| Module | Reference | `with:` arguments |
|--------|-----------|-------------------|
| `shell` | `module: shell` (or `module: builtin.shell`) | `cmd` — the shell command(s) to run |
| `python` | `module: python` (or `module: builtin.python`) | `script` — inline Python, or `script_file` — path to a `.py` file |

`module: shell` and `module: builtin.shell` are equivalent; likewise `module: python` and `module: builtin.python`.

**Shell module** — run a command with `cmd`. The step-level `shell` and `working-directory` fields control the interpreter and cwd:

```yaml
steps:
  - name: port-scan
    module: shell
    with:
      cmd: nmap -sS -p 80,443,8080 {{ inputs.target }}
    shell: /bin/bash
    working-directory: ./scans
    timeout: 30
```

**Python module** — run inline Python with `script`, or a Python file with `script_file`:

```yaml
steps:
  - name: process-results
    module: python
    with:
      script: |
        import json
        data = {"target": "{{ inputs.target }}", "status": "complete"}
        with open("{{ ctx.output_path }}/summary.json", "w") as f:
          json.dump(data, f, indent=2)
        add_outputs(summary_path="{{ ctx.output_path }}/summary.json")

  - name: run-analysis
    module: python
    with:
      script_file: scripts/analyze_results.py
    env:
      THRESHOLD: "0.95"
```

Python modules get these globals injected: `__job__`, `__step__`, `__workflow__`, `__inputs__`, `__ctx__`, `__secrets__`, plus `add_outputs(**kwargs)`, `publish(channel, data)`, `subscribe(channel)`, `wait_for(channel, condition, timeout=60)`, and `export_typed_outputs(project_path, items, prefix="")`. See [Outputs](outputs.md) for `add_outputs` and typed outputs.

### User-defined function (UDF) modules

Point `module:` at a Python file and (optionally) a function inside it:

```yaml
steps:
  - module: modules/port_scan.py::run
    name: port-scan
    with:
      target: "{{ inputs.target }}"
      ports: "80,443,8080"
```

- `module: path/to/my_module.py::my_func` — the `::my_func` part is optional; it defaults to `run`.
- Relative paths resolve **against the workflow directory first, then the current working directory**. Absolute paths are used as-is.

The function receives a single `ctx` argument:

```python
# modules/port_scan.py
def run(ctx):
    target = ctx.inputs["target"]          # the `with:` arguments
    ports = ctx.inputs.get("ports", "1-1000")
    ...
    ctx.add_outputs(port_count=len(ports)) # write step outputs
    ctx.log("scan complete")               # log a message
    return {"summary": ...}                # optional dict merged into step outputs
```

`ctx` exposes:

| Attribute / method | Description |
|--------------------|-------------|
| `ctx.inputs` | The `with:` arguments as a dict |
| `ctx.secrets` | Secrets available to the step |
| `ctx.env` | Environment variables for the step |
| `ctx.working_directory` | The step's working directory |
| `ctx.add_outputs(**kwargs)` | Write output keys (JSON-serialized for lists/dicts) |
| `ctx.log(msg)` | Emit a log line for the step |

The function returns `None` or a `dict` — a returned dict is merged into the step's outputs. If the function raises, the step fails and the traceback is captured in the error output (see [Step errors](#step-errors)).

**Multiple arguments** — pass any number of `with:` keys; they arrive as `ctx.inputs`:

```yaml
- module: modules/http_probe.py
  name: http-probe
  with:
    targets: "a.com,b.com,c.com"          # comma-separated
    timeout: 10
```

**Credential storage** — modules that emit `user_account` typed outputs can auto-store them:

```yaml
- module: modules/username_check.py
  store-creds: true
  with:
    target: "username"
```

### Remote modules

Publish reusable modules in a GitHub repo so others can reference them by namespace:

```yaml
steps:
  - module: anhhung04.ofx-modules.parse_nmap
    name: parse-nmap
    with:
      xml_file: "{{ env.OFX_RUN_DIR }}/nmap.xml"

  - module: anhhung04.ofx-modules.parse_nmap@v1.2.0::analyze
    name: analyze
```

A publisher's repo layout:

```
<repo>/                       # e.g. github.com/anhhung04/ofx-modules
  ofx-modules.yml             # manifest (required)
  modules/
    parse_nmap.py             # def run(ctx) — same ModuleContext contract as local UDFs
    kerberoast.py
```

The manifest declares each module and its entry point:

```yaml
name: ofx-modules
version: 1.2.0
description: Recon/parsing modules for OFX
modules:
  parse_nmap:                        # key = module name used in the spec
    description: Parse nmap XML into hosts/ports
    entry: modules/parse_nmap.py     # optional; default modules/<name>.py
    function: run                    # optional; default run
```

Repos are cloned on first use into the local module cache
(`~/.ofx/modules/<owner>/<repo>[@<ref>]`; override the root with
`OFX_MODULES_DIR`). Pinned refs (`@v1.2.0`) are immutable — one clone per
ref, never auto-updated. Unpinned clones are reused as-is and refreshed
with [`ofx flow modules update`](../../cli/commands/modules.md).

Manage the cache with `ofx flow modules list | add | update | remove`
(see [flow modules](../../cli/commands/modules.md)).

!!! warning "Remote modules are arbitrary code"
    A remote module is fetched over the network and executed locally (or
    streamed to a cloud/session runner) as Python. OFX is a red team tool
    and does **not** sandbox module code: only reference repos you trust,
    and prefer pinning `@<tag>` so the code cannot change under you.

### Typed outputs

Modules produce both raw `stdout` and structured `typed_outputs` (Port, Url, Vulnerability, Certificate, Exploit, UserAccount, etc.). A Python/UDF module emits typed outputs by writing a list of `_type`-tagged dicts, e.g. `add_outputs(typed_outputs=[{'_type': 'port', 'host': h, 'port': p}])` or `ctx.add_outputs(typed_outputs=[...])`. They are accessible via template helpers:

```yaml
- module: shell
  with:
    cmd: |
      echo "Ports: {{ ports(steps['port-scan'].outputs.typed_outputs) | map(attribute='host_port') | join(', ') }}"
      echo "Vulns: {{ vulns(steps['vuln-scan'].outputs.typed_outputs) | length }}"
```

See [Outputs → Typed outputs](outputs.md#typed-outputs) for the full type list and helpers.

### Migrating from `run` / `script` / `script_file`

| Legacy step | Module equivalent |
|-------------|-------------------|
| `run: <cmd>` | `module: shell` + `with: {cmd: <cmd>}` |
| `script: <inline python>` | `module: python` + `with: {script: <inline python>}` |
| `script_file: <path.py>` | `module: python` + `with: {script_file: <path.py>}` |

All other step fields (`name`, `if`/`run_if`, `env`, `retry`, `retry-delay`, `timeout`, `continue-on-error`, `shell`, `working-directory`, `log-stdout`, `log-command`, `with`, `secrets`, `interactive`) are unchanged.

---

## Python Modules and Inter-Job Communication

`module: python` steps execute inline Python code. They have access to workflow context, environment variables, and special functions for inter-job communication.

### Available Variables in Python Modules

Python modules automatically have access to:
- `__job__`: The current job model object
- `__step__`: The current step model object  
- `__workflow__`: The current workflow model object
- `__inputs__`: The workflow inputs
- `__ctx__`: The run context object
- `__secrets__`: The secrets available to the step

### Channel Communication Functions

Python modules can communicate between jobs using channel functions:

- `publish(channel, data)`: Publish data to a named channel
- `subscribe(channel)`: Returns a generator that yields data when it changes (auto-emit)
- `wait_for(channel, condition, timeout=60)`: Wait for data matching a condition

### Example: Inter-Job Communication
```yaml
name: Channel Communication Example
jobs:
  producer:
    steps:
      - name: Send data
        module: python
        with:
          script: |
            publish('results', {'status': 'complete', 'data': [1, 2, 3]})

  consumer:
    needs: producer
    steps:
      - name: Receive data
        module: python
        with:
          script: |
            # Wait for data
            data = wait_for('results', lambda d: d.get('status') == 'complete')
            print(f"Received: {data}")

      - name: Subscribe to changes
        module: python
        with:
          script: |
            # Subscribe returns a generator
            gen = subscribe('results')
            for update in gen:
                print(f"Update: {update}")
                if update.get('status') == 'complete':
                    break
```

Channels are scoped to the workflow level and allow jobs to coordinate asynchronously.

---

## Retries and Branching

Transient failures are common in red team operations (rate limits, flaky targets, dropped shells). Combine step-level `retry` with `if:` conditions to retry an exploit attempt and then branch on its outcome.

### Retry with exponential backoff

`retry` sets the number of retry attempts after the first failure; `retry-delay` (alias `retry_delay`) is the base delay in seconds. Delays grow exponentially (`base * 2^attempt`) with random jitter, capped at 5 minutes:

```yaml
steps:
  - name: exploit-attempt
    module: modules/exploit.py
    with:
      target: "{{ inputs.target }}"
    retry: 3
    retry-delay: 5
```

With `retry: 3` the step runs up to 4 times (1 initial + 3 retries); the per-attempt errors are collected and listed in the final failure message.

### Branching on outcome

`if:` (alias `run_if`) evaluates **after** the step's dependencies complete and inspects their status:

| Condition | Runs when... |
|-----------|--------------|
| `success()` | All dependencies succeeded (default) |
| `failure()` | Any dependency failed |
| `canceled()` | Any dependency was canceled (e.g. its `if:` skipped it) |
| `always()` | Regardless of dependency outcomes |
| Jinja2 expression | Expression evaluates truthy |

### Retry-then-branch chain

The canonical red team pattern — retry the exploit, then loot on success or fall back on failure:

```yaml
name: Exploit with Fallback
jobs:
  exploit:
    steps:
      - name: exploit-attempt
        module: modules/exploit.py
        with:
          target: "{{ inputs.target }}"
        retry: 2
        retry-delay: 5

      - name: collect-loot
        module: shell
        if: success()
        with:
          cmd: ./loot.sh --session {{ steps['exploit-attempt'].outputs.session_id }}

      - name: fallback-exploit
        module: modules/fallback_exploit.py
        if: failure()
        with:
          target: "{{ inputs.target }}"

      - name: report-failure
        module: shell
        if: failure()
        with:
          cmd: echo "Primary exploit failed" | notify
        continue-on-error: true
```

Here the loot step only runs when `exploit-attempt` succeeds; if all retries fail, the fallback module and a failure notification run instead.

---

## Step errors

When a step fails, the error output includes:

- The **exit code** of the failed attempt (or the exception for Python/UDF modules, with traceback)
- The **stderr tail** from the failing attempt
- A **per-attempt retry error list** when `retry` is set, e.g. `Attempts: attempt 1: ...; attempt 2: ...`

```text
Step 'exploit-attempt' failed after 3 attempt(s).
Last error: exit code 1 (stderr tail): connection reset by peer
  Attempts: attempt 1: exit code 1: connection reset by peer; attempt 2: timeout; attempt 3: exit code 1: connection reset by peer
If transient, increase 'retry' count. If permanent, fix the root cause before retrying.
```

Failed step outputs are **not** preserved unless the step has `continue-on-error: true`.

---

## See Also
- [Jobs](jobs.md)
- [Outputs](outputs.md)
- [Script files](script-file.md)
