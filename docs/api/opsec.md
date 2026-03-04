# OPSEC API

The `ofx.api.opsec` module provides operational security helpers: proxy configuration, log and artifact cleanup, timing controls, and traffic blending to reduce detection risk during engagements.

---

## Submodules

| Submodule | Purpose |
|-----------|---------|
| `opsec.proxy` | Proxychains configuration and HTTP proxy environment variables |
| `opsec.cleanup` | History, log, and artefact removal commands |
| `opsec.timing` | Business-hour checks and randomised sleep helpers |
| `opsec.traffic` | User-agent rotation, header blending, domain fronting |

---

## Proxy (`opsec.proxy`)

### `build_proxychains_conf(proxies, *, proxy_type="socks5", timeout=5000) -> str`

Generate a `proxychains.conf` file content for a list of proxy hosts.

```python
from ofx.api.opsec import build_proxychains_conf

conf = build_proxychains_conf(["127.0.0.1:9050", "10.0.0.3:1080"])
print(conf)
```

### `http_proxy_env(host, port, *, scheme="http") -> dict[str, str]`

Return a `dict` of environment variables (`HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy`, `https_proxy`) suitable for passing to `subprocess.run(env=...)`.

```python
from ofx.api.opsec import http_proxy_env

env_vars = http_proxy_env("127.0.0.1", 8080)
```

---

## Cleanup (`opsec.cleanup`)

### `clean_history_commands() -> list[str]`

Shell commands to wipe bash/zsh history on Linux.

### `clean_linux_logs(*, include_wtmp=True) -> list[str]`

Commands to truncate common Linux log files (`/var/log/auth.log`, syslog, wtmp, btmp, lastlog).

### `clean_windows_artifacts() -> list[str]`

PowerShell commands to clear Windows event logs and prefetch files.

### `timestomp_command(path, *, reference="/etc/hosts") -> str`

Return a `touch` command that copies timestamps from a reference file, hiding the modification time of `path`.

### `remove_ssh_known_host(hostname) -> str`

Return a `ssh-keygen -R` command to remove a host from `~/.ssh/known_hosts`.

### `secure_delete_command(path, *, passes=3) -> str`

Return a `shred` command for secure multi-pass overwrite on Linux.

```python
from ofx.api.opsec import clean_history_commands, timestomp_command

for cmd in clean_history_commands():
    print(cmd)

print(timestomp_command("/tmp/beacon.elf"))
```

---

## Timing (`opsec.timing`)

### `is_business_hours(*, tz_offset=0, start=9, end=17) -> bool`

Return `True` if the current UTC+offset time falls within working hours. Use to gate noisy operations.

### `random_sleep_seconds(min_s=30, max_s=300) -> float`

Return a random float in `[min_s, max_s]` for jittered sleep between operations.

```python
import time
from ofx.api.opsec import is_business_hours, random_sleep_seconds

if not is_business_hours(tz_offset=-5):
    time.sleep(random_sleep_seconds(60, 600))
```

---

## Traffic Blending (`opsec.traffic`)

### `rotate_user_agent() -> str`

Return a randomly selected realistic browser User-Agent string.

### `traffic_blend_headers() -> dict[str, str]`

Return a dict of common HTTP headers that blend traffic with legitimate browser requests.

### `domain_fronting_headers(front_domain, real_host) -> dict[str, str]`

Build HTTP headers for a domain-fronting request: `Host` is set to `front_domain` while `X-Forwarded-Host` carries `real_host`.

### `cdncheck_command(domain) -> str`

Return a `curl` command to probe whether a domain is behind a CDN.

```python
from ofx.api.opsec import rotate_user_agent, traffic_blend_headers

import requests
headers = traffic_blend_headers()
headers["User-Agent"] = rotate_user_agent()
resp = requests.get("https://target.com", headers=headers)
```

---

## Workflow Snippet

```yaml
jobs:
  opsec-check:
    steps:
      - name: clean tracks
        script: |
          from ofx.api.opsec import clean_history_commands, clean_linux_logs
          import subprocess

          for cmd in clean_history_commands() + clean_linux_logs():
              subprocess.run(cmd, shell=True)
```

---

## See Also

- [Evasion API](evasion.md) — AV/EDR bypass, payload obfuscation
- [Persistence API](persistence.md) — Establish footholds
