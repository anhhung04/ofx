# flow tasks

List, inspect, and run registered task wrappers.

## Subcommands

| Command | Description |
|---------|-------------|
| `ofx flow tasks list` | List all registered tasks |
| `ofx flow tasks info <name>` | Show detailed task information |
| `ofx flow tasks run <name> <target>` | Run a task directly from the CLI |

---

## list

List all registered tasks with their category, description, and install status.

### Usage

```bash
ofx flow tasks list [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `-c, --category <prefix>` | Filter tasks by category prefix (e.g. `port/`, `dns/`, `url/`, `vuln/`) |

### Examples

```bash
# List all tasks
ofx flow tasks list

# Filter by category
ofx flow tasks list -c port/
ofx flow tasks list -c dns/
ofx flow tasks list -c vuln/
ofx flow tasks list -c url/crawl
```

---

## info

Show detailed information about a specific task, including its options, output types, install status, and example YAML usage.

### Usage

```bash
ofx flow tasks info <task_name>
```

### Examples

```bash
ofx flow tasks info nmap
ofx flow tasks info httpx
ofx flow tasks info nuclei
```

### Output

Displays:

- Task metadata (name, category, binary, install status)
- Output types produced
- Options table (name, flag, type, description)
- Install command (if defined)
- Example YAML snippet

---

## run

Run a single task directly from the command line without writing a YAML workflow file. This is useful for quick one-off scans, testing tool configurations, and exploring task options.

### Usage

```bash
ofx flow tasks run <task_name> <target> [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `task_name` | Name of the registered task (e.g. `nmap`, `httpx`, `nuclei`) |
| `target` | Target for the task — IP, domain, URL, CIDR, or file path |

### Options

| Option | Description |
|--------|-------------|
| `-o, --opt key=value` | Task option as `key=value` or `key` (boolean flag). Repeatable. |
| `--profile <name>` | Execution profile to apply (injects proxy, threads, rate_limit, etc.) |
| `--timeout <minutes>` | Timeout in minutes (default: 60) |
| `--output <dir>` | Directory to store output files |
| `--store-creds` | Store discovered `UserAccount` credentials in the credential store |
| `--json` | Output results as JSON instead of Rich tables |

### Option Parsing

The `--opt` flag supports several value formats:

| Format | Result |
|--------|--------|
| `key=value` | String value (auto-coerced to int/float/bool when possible) |
| `key=true` / `key=false` | Boolean |
| `key=42` | Integer |
| `key` (no `=`) | Boolean `true` (flag mode) |

### Examples

```bash
# Basic port scan
ofx flow tasks run nmap 10.10.10.5 --opt ports=1-1000 --opt timing=T4

# HTTP probing with threading
ofx flow tasks run httpx targets.txt --opt threads=50 --opt tech_detect

# Vulnerability scan with profile
ofx flow tasks run nuclei https://example.com --profile stealth

# Subdomain enumeration with JSON output
ofx flow tasks run subfinder example.com --json

# Directory fuzzing with wordlist
ofx flow tasks run ffuf https://example.com/FUZZ \
  --opt wordlist=/usr/share/seclists/Discovery/Web-Content/common.txt \
  --opt threads=50

# Run with output directory
ofx flow tasks run nmap 10.0.0.0/24 --opt top_ports=1000 --output ./results/

# Store discovered credentials
ofx flow tasks run hydra 10.10.10.5 \
  --opt service=ssh --opt username=admin \
  --opt password=/usr/share/wordlists/rockyou.txt \
  --store-creds
```

### Profile Integration

When `--profile` is specified, OFX automatically maps profile-level settings to matching task options. See [Profiles — Automatic Task Option Injection](../../guide/profiles.md#automatic-task-option-injection) for details.

```bash
# Create a stealth profile
ofx flow profile add stealth --set threads=2 --set rate_limit=30 --set proxy=socks5://127.0.0.1:9050

# Run with profile — threads, rate_limit, and proxy are auto-injected
ofx flow tasks run httpx example.com --profile stealth
```

### Output Display

By default, results are displayed as Rich tables grouped by output type (ports, URLs, vulnerabilities, etc.). Use `--json` for machine-readable output.

**Rich output example:**
```
Running task: httpx target=example.com

              url (3)
┌──────────────────────────────┬─────────────┬────────────────┐
│ url                          │ status_code │ title          │
├──────────────────────────────┼─────────────┼────────────────┤
│ https://example.com          │ 200         │ Example Domain │
│ http://example.com           │ 301         │                │
│ https://www.example.com      │ 200         │ Example Domain │
└──────────────────────────────┴─────────────┴────────────────┘

✓ 3 results (3 url)
```

**JSON output example:**
```json
{
  "status": "success",
  "exit_code": 0,
  "typed_outputs": [
    {"_type": "url", "url": "https://example.com", "status_code": 200, "title": "Example Domain"}
  ],
  "stdout": "..."
}
```

---

## See Also

- [Tasks Guide](../../guide/tasks.md) — Task system overview and YAML usage
- [Profiles](../../guide/profiles.md) — Execution profiles with auto-injection
- [Run Command](run.md) — Running full workflow files
