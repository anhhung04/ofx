# Privilege Escalation API

The `ofx.api.privesc` module generates command strings for local privilege escalation checks and exploitation on Linux and Windows systems.

!!! warning
    All functions return **command strings** — nothing is executed locally. Pass them to a [post runner](#) or your own execution mechanism.

---

## Submodules

| Submodule | Purpose |
|-----------|---------|
| `privesc.linux` | SUID, sudo, capabilities, container escapes, cron |
| `privesc.windows` | UAC bypass, token abuse, service misconfigs, DPAPI |

---

## Linux (`privesc.linux`)

### `suid_commands() -> list[str]`

Return `find` commands to locate SUID/SGID binaries.

### `capabilities_command() -> str`

Return a `getcap -r /` command to list files with elevated Linux capabilities.

### `sudo_check_command() -> str`

Return `sudo -l` to enumerate allowed sudo commands for the current user.

### `crontab_persistence() -> list[str]`

Return commands to enumerate world-writable cron scripts and jobs.

### `writable_systemd_command() -> str`

Return a `find` command to locate world-writable systemd unit files.

### `docker_escape_commands() -> list[str]`

Return commands to detect Docker socket exposure and perform container escape via mounted socket.

### `lxd_escape_commands() -> list[str]`

Return commands to exploit LXD group membership for host filesystem access.

### `nfs_check_commands() -> list[str]`

Return commands to detect NFS `no_root_squash` shares.

### `path_hijack_check_commands() -> list[str]`

Return commands to find writable directories in `$PATH` ahead of system binaries.

### `writable_passwd_command() -> str`

Return a command to check whether `/etc/passwd` is world-writable.

### `kernel_exploit_check_command() -> str`

Return `uname -r` (used to cross-reference against known kernel exploits).

```python
from ofx.api.privesc import suid_commands, sudo_check_command, docker_escape_commands

for cmd in suid_commands():
    print(cmd)
print(sudo_check_command())
for cmd in docker_escape_commands():
    print(cmd)
```

---

## Windows (`privesc.windows`)

### `uac_bypass_commands(method="fodhelper") -> list[str]`

Return PowerShell commands for a UAC bypass. Supported methods: `fodhelper`, `eventvwr`.

### `token_privileges_commands() -> list[str]`

Return PowerShell commands to enumerate and abuse token privileges (SeImpersonatePrivilege, SeDebugPrivilege).

### `unquoted_service_path_command() -> str`

Return a `wmic` command to find services with unquoted paths.

### `alwaysinstallelevated_commands() -> list[str]`

Return `reg query` commands to detect the `AlwaysInstallElevated` misconfiguration.

### `weak_service_permissions_command() -> str`

Return an `accesschk` command to find services the current user can modify.

### `credential_files_commands() -> list[str]`

Return PowerShell and `dir` commands to hunt for stored credential files (Unattend.xml, SAM backups, etc.).

### `dpapi_commands(sid=None) -> list[str]`

Return `mimikatz` DPAPI decryption commands for the given SID (or current user if `None`).

### `printspoofer_command(cmd="cmd") -> str`

Return a `PrintSpoofer.exe` command to escalate from `SeImpersonatePrivilege`.

### `juicy_potato_command(cmd="cmd", *, clsid=None) -> str`

Return a `JuicyPotato.exe` command for COM impersonation token abuse.

### `registry_autorun_commands() -> list[str]`

Return `reg query` commands to enumerate autorun registry keys for writable values.

```python
from ofx.api.privesc import (
    uac_bypass_commands,
    unquoted_service_path_command,
    credential_files_commands,
)

for cmd in uac_bypass_commands("fodhelper"):
    print(cmd)
print(unquoted_service_path_command())
```

---

## Workflow Snippet

```yaml
jobs:
  privesc-check:
    steps:
      - name: linux privesc enum
        script: |
          from ofx.api.privesc import suid_commands, sudo_check_command
          from ofx.api.post.runners.ssh import PostSSH

          runner = PostSSH(host="{{ inputs.target }}", user="{{ secrets.user }}")
          for cmd in suid_commands():
              output = runner.run(cmd)
              if output.strip():
                  print(f"[SUID] {output}")
          print(runner.run(sudo_check_command()))
```

---

## See Also

- [AD API](ad.md) — Domain privilege escalation
- [Persistence API](persistence.md) — Establish footholds after escalation
- [Post Runners](#) — Remote execution
