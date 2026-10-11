# Running Python scripts with `module: python` + `with: script_file`

`with: script_file` lets a `module: python` step run a Python file directly (without embedding the code in YAML) while still using the workflow's context, env vars, and secrets.

```yaml
name: Script File Example
jobs:
  run-script:
    steps:
      - name: Run helper
        module: python
        with:
          script_file: scripts/my_helper.py
        env:
          HELLO: world
```

## How it resolves paths

- If the path is **relative**, it is resolved against the workflow directory (`workflow_dir`).
- If the path is **absolute**, it is used as-is.
- If the file has no `.py` suffix, `.py` is appended.
- The script runs with the step's `working_directory` (default: current working directory).

With a workflow directory like `workflows/`, the step above executes `workflows/scripts/my_helper.py`.

## Example (absolute path)

```yaml
steps:
  - name: Run absolute script
    module: python
    with:
      script_file: /tmp/custom_task.py
```

## Using workflow context, env, and secrets

Your script can import `ofx` modules and external dependencies already installed in the environment. Environment variables and secrets provided to the step are available in the process environment.

Python files executed via `script_file` have access to the same injected variables and channel communication functions as inline `script` steps.

### Available Variables in Scripts

- `__job__`: The current job model object
- `__step__`: The current step model object
- `__workflow__`: The current workflow model object
- `__inputs__`: The workflow inputs
- `__ctx__`: The run context object
- `__secrets__`: The secrets available to the step

### Channel Communication Functions

- `publish(channel, data)`: Publish data to a named channel
- `subscribe(channel)`: Returns a generator that yields data when it changes
- `wait_for(channel, condition, timeout=60)`: Wait for data matching a condition

```python
#!/usr/bin/env python3
import os
from ofx.settings import settings

print(f"Brand: {settings.app_branding}")
print(f"HELLO env: {os.getenv('HELLO')}")

# Inter-job communication
publish('status', {'state': 'running'})
data = wait_for('config', lambda d: d.get('ready'))
```

## Failure cases

- The file must exist after resolution; otherwise the step fails with `FileNotFoundError`.
- Only Python files are supported for `script_file`; other interpreters should use `module: shell` with `cmd`.

## Testing

See the automated coverage in `tests/test_script_file.py`, which validates:
- relative resolution against `workflow_dir`
- absolute paths
- importing `ofx` modules and external dependencies