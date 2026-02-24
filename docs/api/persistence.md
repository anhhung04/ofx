# Persistence API

Craft common Windows persistence commands for use with remote runners.

## Functions

- `schtask_command(name, cmd, trigger="ONLOGON", user=None) -> str`: Create a scheduled task command.
- `service_command(name, bin_path, display_name=None) -> str`: Build a service creation command.
- `runkey_command(name, value, hive="HKCU") -> str`: Build a Run key addition command.

## Python Usage

```python
from ofx.api import persistence
cmd = persistence.schtask_command("Updater", r"C:\\Temp\\b.exe")
print(cmd)
```

## Workflow Snippet

```yaml
steps:
  - name: add schtask
    run: |
      python - <<'PY'
      from ofx.api import persistence
      cmd = persistence.schtask_command("Updater", r"C:\\Temp\\b.exe")
      print(cmd)
      PY
```
