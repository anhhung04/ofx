# Running Python scripts with `script_file`

`script_file` lets a step run a Python file directly (without embedding the code in YAML) while still using the workflow’s context, env vars, and secrets.

## How it resolves paths

- If the path is **relative**, it is resolved against the workflow directory (`workflow_dir`).
- If the path is **absolute**, it is used as-is.
- If the file has no `.py` suffix, `.py` is appended.
- The runner changes the working directory to the script’s parent before execution.

## Example (relative path)

```yaml
name: Script File Example
jobs:
  run-script:
    steps:
      - name: Run helper
        script_file: scripts/my_helper
        env:
          HELLO: world
```

With a workflow directory like `workflows/`, the step will execute `workflows/scripts/my_helper.py`.

## Example (absolute path)

```yaml
steps:
  - name: Run absolute script
    script_file: /tmp/custom_task.py
```

## Using workflow context, envs, and secrets

Your script can import `ofx` modules and external dependencies already installed in the environment. Environment variables and secrets provided to the step are available in the process environment.

```python
#!/usr/bin/env python3
import os
from ofx.settings import settings

print(f"Brand: {settings.app_branding}")
print(f"HELLO env: {os.getenv('HELLO')}")
```

## Failure cases

- The file must exist after resolution; otherwise the step fails with `FileNotFoundError`.
- Only Python scripts are supported for `script_file`; other interpreters should use `run` or `run_file`.

## Testing

See the automated coverage in `tests/test_script_file.py`, which validates:
- relative resolution against `workflow_dir`
- absolute paths
- importing `ofx` modules and external dependencies
