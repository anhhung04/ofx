# Profiles

Profiles are **reusable option presets** that control execution behavior — rate limits, stealth settings, time windows, and per-tool option overrides. They are stored in `~/.ofx/profiles.yml` and applied to workflows via the `defaults.profile` field.

---

## Quick Start

Create a stealth profile:
```bash
ofx flow profile add stealth \
  --desc "Slow & quiet scanning" \
  --set rate_limit=30 \
  --set delay=2.0 \
  --set jitter=1.0 \
  --set threads=2 \
  --set time_window.enabled=true \
  --set time_window.start=09:00 \
  --set time_window.end=17:00 \
  --set "time_window.days=[monday,tuesday,wednesday,thursday,friday]"
```

Use it in a workflow:
```yaml
name: Stealth Recon
defaults:
  profile: stealth

jobs:
  scan:
    steps:
      - task: nmap
        with:
          target: "{{ inputs.target }}"
```

---

## Profile Settings

### Rate & Intensity

| Field | Default | Description |
|-------|---------|-------------|
| `rate_limit` | `0` (unlimited) | Max requests per minute |
| `max_retries` | `3` | Default retry count for failing steps |
| `timeout_minutes` | `60` | Default step timeout in minutes |
| `threads` | `10` | Default concurrency for tools |

### Stealth / OPSEC

| Field | Default | Description |
|-------|---------|-------------|
| `delay` | `0.0` | Delay between requests (seconds) |
| `jitter` | `0.0` | Random jitter added to delay (seconds) |
| `user_agent` | `""` | Custom User-Agent string |
| `proxy` | `""` | Proxy URL (e.g. `socks5://127.0.0.1:9050`) |

### Time Window

| Field | Default | Description |
|-------|---------|-------------|
| `time_window.enabled` | `false` | Activate time window enforcement |
| `time_window.start` | `"00:00"` | Window start (HH:MM, 24h) |
| `time_window.end` | `"23:59"` | Window end (HH:MM, 24h) |
| `time_window.days` | all 7 days | Allowed days (lowercase English) |
| `time_window.timezone` | `"UTC"` | IANA timezone name |
| `time_window.warn_before_minutes` | `10` | Minutes before end to warn |
| `time_window.abort_on_expire` | `true` | Abort workflow when window closes |

### Task Option Overrides

Override default options for specific tasks:

```yaml
profiles:
  stealth:
    task_options:
      nmap:
        timing: "T2"
      httpx:
        rate_limit: 10
        threads: 2
      nuclei:
        rate_limit: 20
```

### Environment Variables

Inject env vars into all jobs:

```yaml
profiles:
  tor:
    proxy: "socks5://127.0.0.1:9050"
    env:
      HTTP_PROXY: "socks5://127.0.0.1:9050"
      HTTPS_PROXY: "socks5://127.0.0.1:9050"
```

### Auto-Injected Environment Variables

When a profile is active, OFX automatically injects `OFX_*` environment variables from non-default profile fields. These are available in all steps and can be read by external tools:

| Variable | Source Field | Injected When |
|----------|-------------|---------------|
| `OFX_RATE_LIMIT` | `rate_limit` | `rate_limit > 0` |
| `OFX_THREADS` | `threads` | `threads ≠ 10` (non-default) |
| `OFX_TIMEOUT` | `timeout_minutes` | `timeout_minutes ≠ 60` (non-default) |
| `OFX_DELAY` | `delay` | `delay > 0` |
| `OFX_JITTER` | `jitter` | `jitter > 0` |
| `OFX_PROXY` | `proxy` | `proxy` is set |
| `OFX_USER_AGENT` | `user_agent` | `user_agent` is set |

These are in addition to any custom `env:` vars defined in the profile.

---

## Time Window Enforcement

When a profile has `time_window.enabled: true`, OFX enforces execution timing:

### Pre-run Check

Before the workflow starts, the current time/day is checked against the window. If outside the allowed window, the workflow **immediately aborts** with a clear error:

```
Workflow aborted: Current time 22:15 UTC is outside the allowed window
(09:00–17:00). Profile 'stealth' restricts execution to Monday–Friday (US/Eastern).
```

### During Execution

A **background monitor** checks the time window every 30 seconds:

1. **Warning** — When approaching the window end (configurable via `warn_before_minutes`):
   ```
   ⚠️  Only 8 minutes remaining in execution window (09:00–17:00 US/Eastern)
   ```

2. **Abort** — When the window expires (if `abort_on_expire: true`):
   ```
   🛑 Time window expired — workflow will be aborted
   ```
   Remaining stages are skipped and the workflow fails with a clear error.

### Overnight Windows

Overnight windows (e.g. `22:00`–`06:00`) are supported:

```yaml
profiles:
  night-ops:
    time_window:
      enabled: true
      start: "22:00"
      end: "06:00"
      timezone: "US/Eastern"
```

---

## CLI Commands

### List profiles

```bash
ofx flow profile list
```

### Show profile details

```bash
ofx flow profile show stealth
```

### Add/update a profile

```bash
ofx flow profile add <name> [--desc "..."] [--set key=value]...
```

Supports dot notation for nested fields:
```bash
ofx flow profile add fast \
  --set rate_limit=0 \
  --set threads=50 \
  --set time_window.enabled=false
```

### Remove a profile

```bash
ofx flow profile remove <name>
```

### Set default profile

```bash
ofx flow profile default <name>
```

The default profile is automatically applied to all workflows that don't specify one.

---

## Example Profiles

### Aggressive (internal network)

```yaml
aggressive:
  description: "Maximum speed for internal networks"
  rate_limit: 0
  threads: 50
  timeout_minutes: 30
  task_options:
    nmap:
      timing: "T5"
    naabu:
      rate: 10000
```

### Stealth (external, business hours)

```yaml
stealth:
  description: "Slow & quiet, business hours only"
  rate_limit: 30
  delay: 2.0
  jitter: 1.0
  threads: 2
  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
  time_window:
    enabled: true
    start: "09:00"
    end: "17:00"
    days: [monday, tuesday, wednesday, thursday, friday]
    timezone: US/Eastern
    warn_before_minutes: 15
  task_options:
    nmap:
      timing: "T2"
```

### Tor (anonymous)

```yaml
tor:
  description: "Route traffic through Tor"
  proxy: "socks5://127.0.0.1:9050"
  delay: 3.0
  threads: 3
  env:
    HTTP_PROXY: "socks5://127.0.0.1:9050"
    HTTPS_PROXY: "socks5://127.0.0.1:9050"
```

---

## File Format

Profiles are stored in `~/.ofx/profiles.yml`:

```yaml
profiles:
  stealth:
    description: "Slow & quiet"
    rate_limit: 30
    # ... other settings

  aggressive:
    rate_limit: 0
    threads: 50

defaults:
  profile: stealth
```

---

## Accessing Profile Data in Templates

When a profile is active, its settings are available in templates via `{{ profile.* }}`:

```yaml
steps:
  - run: |
      echo "Rate limit: {{ profile.rate_limit }}"
      echo "Threads: {{ profile.threads }}"
      {% if profile.proxy %}
      echo "Using proxy: {{ profile.proxy }}"
      {% endif %}
```
