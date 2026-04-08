# Tasks

Tasks are **pre-built security tool wrappers** that provide structured output parsing, option mapping, and install logic for common offensive tools. They are inspired by [secator](https://github.com/freelabz/secator)'s task architecture and integrate natively into OFX workflows.

---

## Quick Start

```yaml
name: Recon Pipeline
jobs:
  recon:
    steps:
      - task: nmap
        name: port-scan
        with:
          target: "{{ inputs.target }}"
          ports: "1-1000"
          version_detection: true

      - task: httpx
        name: probe-http
        with:
          target: "{{ inputs.target }}"
          tech_detect: true
```

Run with:
```bash
ofx flow run recon.yml --input target=192.168.1.0/24
```

---

## How Tasks Work

A `task:` step references a registered tool wrapper by name. The wrapper:

1. **Maps options** — Translates `with:` keys into CLI flags (e.g. `ports: "80,443"` → `-p 80,443`)
2. **Executes the tool** — Runs the command and captures output
3. **Parses output** — Converts raw stdout/files into **structured typed outputs** (Port, Url, Vulnerability, etc.)
4. **Stores results** — Both raw `stdout` and `typed_outputs` are saved to the registry for use by later steps

### Syntax

```yaml
- task: <tool_name>
  name: <optional step name>
  with:
    target: "<target>"
    <option>: <value>
    ...
```

The `with:` block provides:

- `target` (required) — The primary target (IP, URL, domain, CIDR)
- Tool-specific options — Mapped to CLI flags by the task definition

---

## Available Tasks

List all registered tasks:
```bash
ofx flow tasks list
```

Get details about a specific task:
```bash
ofx flow tasks info nmap
```

Filter by category:
```bash
ofx flow tasks list -c port/
ofx flow tasks list -c dns/
ofx flow tasks list -c url/
ofx flow tasks list -c vuln/
```

### Running Tasks from the CLI

You can run any task directly from the command line without writing a YAML workflow:

```bash
ofx flow tasks run <task_name> <target> [--opt key=value]...
```

**Examples:**

```bash
# Port scan
ofx flow tasks run nmap 10.10.10.5 --opt ports=1-1000 --opt timing=T4

# HTTP probing with custom threads
ofx flow tasks run httpx targets.txt --opt threads=50 --opt tech_detect

# Vulnerability scan with a profile
ofx flow tasks run nuclei https://example.com --profile stealth

# Subdomain enum with JSON output
ofx flow tasks run subfinder example.com --json
```

Options:

| Flag | Description |
|------|-------------|
| `-o, --opt key=value` | Task option (repeatable). Use `key` alone for boolean flags. |
| `--profile <name>` | Apply an execution profile (auto-injects proxy, threads, rate_limit, etc.) |
| `--timeout <min>` | Timeout in minutes (default: 60) |
| `--output <dir>` | Directory for output files |
| `--store-creds` | Store discovered credentials |
| `--json` | Output as JSON |

See the [CLI reference](../cli/commands/tasks.md) for full details.

### Built-in Tasks

| Task | Category | Description | Output Types |
|------|----------|-------------|-------------|
| `nmap` | port/scan | Network port scanner and service detector | Port, Vulnerability |
| `naabu` | port/scan | Fast port scanner written in Go | Port |
| `httpx` | url/probe | Fast and multi-purpose HTTP toolkit | Url, Tag |
| `ffuf` | url/fuzz | Fast web fuzzer written in Go | Url |
| `feroxbuster` | url/fuzz | Fast content discovery tool written in Rust | Url |
| `dirsearch` | url/fuzz | Advanced web path brute-forcer | Url |
| `arjun` | url/fuzz/params | HTTP parameter discovery suite | Url, Tag |
| `dalfox` | url/fuzz | Powerful XSS scanning tool | Vulnerability, Url |
| `katana` | url/crawl | Next-generation crawling and spidering framework | Url |
| `gospider` | url/crawl | Fast web spider written in Go | Url |
| `gau` | url/recon | Fetch known URLs from OTX, Wayback, Common Crawl | Url, Subdomain |
| `subfinder` | dns/recon | Fast passive subdomain enumeration tool | Subdomain |
| `dnsx` | dns/resolve | Fast and multi-purpose DNS toolkit | Subdomain, Ip, Record |
| `nuclei` | vuln/scan | Fast template-based vulnerability scanner | Vulnerability, Tag |
| `grype` | vuln/scan | Vulnerability scanner for container images | Vulnerability |
| `trivy` | vuln/scan | Comprehensive security scanner | Vulnerability, Tag |
| `wpscan` | vuln/scan/wordpress | WordPress security scanner | Vulnerability, Tag |
| `testssl` | dns/recon/tls | SSL/TLS security scanner | Certificate, Vulnerability, Tag |
| `ssh-audit` | ssh/audit | SSH server security auditing | Vulnerability, Tag |
| `gitleaks` | secret/scan | Secret detection in git repositories | Tag |
| `trufflehog` | secret/scan | Secret detection in repos and filesystems | Tag |
| `searchsploit` | exploit/recon | ExploitDB search tool | Exploit |
| `maigret` | user/recon | Username OSINT across social networks | UserAccount |
| `h8mail` | user/recon/email | Email/password breach lookup | UserAccount |
| `whois` | domain/info | Domain WHOIS lookup | Domain |
| `wafw00f` | waf/detect | Web Application Firewall detection tool | Tag |
| `gobuster` | url/fuzz | Directory/file, DNS, and vhost brute-forcer written in Go | Url |
| `amass` | dns/recon | In-depth attack surface mapping and asset discovery | Subdomain |
| `masscan` | port/scan | Massively parallel TCP port scanner | Port, Ip |
| `assetfinder` | dns/recon | Find domains and subdomains related to a given domain | Subdomain |
| `findomain` | dns/recon | Fast subdomain enumeration using certificate transparency | Subdomain |
| `mapcidr` | ip/util | CIDR/IP manipulation and range expansion utility | Ip |
| `fping` | ip/recon | Fast ping sweep for host discovery | Ip |
| `cariddi` | url/crawl | Crawler focused on endpoint and secret discovery | Url, Tag |
| `nikto` | vuln/scan/web | Web server scanner for dangerous files and outdated software | Vulnerability |
| `whatweb` | url/fingerprint | Web technology fingerprinting tool | Tag |
| `sqlmap` | vuln/scan/sqli | Automatic SQL injection detection and exploitation tool | Vulnerability |
| `x8` | url/fuzz/params | Hidden parameter discovery tool written in Rust | Tag |
| `dnsrecon` | dns/recon | DNS enumeration and zone transfer tool | Record, Subdomain |
| `theHarvester` | osint/recon | Email, subdomain, and name harvester from public sources | Subdomain, UserAccount |
| `holehe` | user/recon/email | Check if an email is registered on various websites | UserAccount |
| `sslscan` | ssl/scan | SSL/TLS cipher suite and certificate scanner | Certificate, Vulnerability |
| `netexec` | ad/enum | Network service pentesting (CrackMapExec successor) | UserAccount, Tag |
| `kerbrute` | ad/brute | Kerberos user enum and password spraying | UserAccount |
| `hydra` | brute/login | Network login brute forcer | UserAccount |
| `enum4linux` | ad/enum | SMB/AD enumeration | UserAccount, Tag |
| `paramspider` | url/recon/params | URL parameter mining from web archives | Url |
| `hakrawler` | url/crawl | Fast web crawler | Url |
| `subzy` | vuln/takeover | Subdomain takeover checker | Vulnerability |
| `crlfuzz` | vuln/injection | CRLF injection scanner | Vulnerability |
| `commix` | vuln/injection | Command injection scanner | Vulnerability |
| `rustscan` | port/scan | Ultra-fast port scanner | Port |
| `gowitness` | url/screenshot | Web screenshotting | Url, Tag |
| `jwt_tool` | vuln/jwt | JWT vulnerability testing | Vulnerability, Tag |
| `name-that-hash` | crypto/identify | Hash identification | Tag |
| `hashid` | crypto/identify | Hash identifier | Tag |

---

## Structured Output Types

Tasks produce **typed outputs** — Pydantic models that normalize tool output into a common schema. This enables data chaining between steps.

### Output Type Reference

| Type | Key Fields | Description |
|------|-----------|-------------|
| `Port` | port, ip, host, protocol, service_name, state | An open network port |
| `Url` | url, host, status_code, title, tech, content_type | An HTTP endpoint |
| `Vulnerability` | name, id, severity, matched_at, provider, tags | A detected vulnerability |
| `Subdomain` | host, domain | A discovered subdomain |
| `Ip` | ip, host | An IP address |
| `Tag` | name, value, match, category | A metadata tag (technology, WAF, etc.) |
| `Record` | name, type, host | A DNS record |
| `Domain` | domain, registrar, alive | A domain with registration info |
| `Certificate` | host, subject, issuer, not_before, not_after | A TLS certificate |
| `Exploit` | name, id, url, platform, type | A known exploit |
| `UserAccount` | username, password, hash, domain, host, account_type, privilege_level | A discovered credential/account |

All output types include:

- `extra_data` — Dict for tool-specific fields that don't fit the schema
- `_type` — String discriminator (e.g. `"port"`, `"url"`)
- `_uuid` — Deterministic hash for deduplication

### UserAccount & Credential Integration

The `UserAccount` output type bridges to the `ofx.api.creds.exegol_history.Credential` dataclass, enabling seamless credential management:

```python
# In a script step — convert discovered account to credential store
from ofx.tasks.output_types import UserAccount

account = UserAccount(
    username="admin",
    password="P@ssw0rd!",
    domain="CORP",
    host="10.0.0.1",
    account_type="domain",
    privilege_level="admin",
    source="secretsdump",
)

# Convert to exegol-history Credential for KeePass storage
cred = account.to_credential()

# Or create from existing Credential
account = UserAccount.from_credential(cred, host="DC01", source="mimikatz")
```

### Automatic Credential Storage

Task steps that produce `UserAccount` outputs can automatically store them in the credential store (exegol-history KeePass DB).

**Workflow-level** — enable for all task steps:

```yaml
defaults:
  store-creds: true

jobs:
  brute:
    steps:
      - task: hydra          # credentials auto-stored
        with:
          target: "{{ inputs.target }}"
```

**Step-level** — enable or override per step:

```yaml
steps:
  - task: hydra
    store-creds: true         # enable for this step
    with:
      target: "{{ inputs.target }}"
  - task: netexec
    store-creds: false        # disable even if defaults say true
    with:
      target: "{{ inputs.target }}"
```

**Global** — enable for all workflows via `~/.ofx/config.yml`:

```yaml
auto_store_creds: true
```

**Precedence**: step-level `store-creds` > workflow/job `defaults.store-creds` > global `auto_store_creds`.

Duplicate credentials (same username + password + hash + domain) are automatically skipped. The credential store must be available (exegol-history with `~/.exh/DB.kdbx`); if not, the feature silently skips storage.

---

## Live Streaming

Tasks that output JSONL or line-delimited results support **live streaming** — items are parsed and published to channels as each line arrives, rather than waiting for the entire command to finish.

### How It Works

1. **Line-by-line reading** — `CommandExecutor.execute_streaming()` reads stdout one line at a time via async subprocess pipes
2. **Incremental parsing** — Each line is passed to the task's `parse_line()` method, producing typed output items immediately
3. **Channel publishing** — New items are published to `task:<name>:items` channel for real-time consumption by other steps
4. **Deduplication** — Items are deduplicated incrementally as they arrive

### Streaming-Capable Tools

| Tool | Format | Streaming |
|------|--------|-----------|
| httpx | JSONL | ✅ |
| nuclei | JSONL | ✅ |
| naabu | JSONL | ✅ |
| katana | JSONL | ✅ |
| dnsx | JSONL | ✅ |
| feroxbuster | JSONL | ✅ |
| subfinder | line | ✅ |
| gospider | JSONL | ✅ |
| gau | JSONL | ✅ |
| dalfox | JSONL | ✅ |
| maigret | JSONL | ✅ |
| trufflehog | JSONL | ✅ |
| nmap | XML | ❌ (file-based) |
| ffuf | JSON | ❌ (single blob) |
| wafw00f | stdout | ❌ (multi-line) |
| dirsearch | JSON file | ❌ |
| arjun | JSON file | ❌ |
| gitleaks | JSON file | ❌ |
| grype | JSON blob | ❌ |
| trivy | JSON blob | ❌ |
| wpscan | JSON blob | ❌ |
| ssh-audit | JSON blob | ❌ |
| testssl | JSON file | ❌ |
| searchsploit | JSON blob | ❌ |
| h8mail | JSON file | ❌ |
| whois | text | ❌ |
| gobuster | line | ✅ |
| amass | JSONL | ✅ |
| masscan | JSONL | ✅ |
| assetfinder | line | ✅ |
| findomain | line | ✅ |
| mapcidr | line | ✅ |
| fping | line | ✅ |
| cariddi | JSONL | ✅ |
| nikto | CSV | ❌ (multi-line) |
| whatweb | JSON blob | ❌ |
| sqlmap | text | ❌ (multi-line) |
| x8 | JSONL | ✅ |
| dnsrecon | JSON blob | ❌ |
| theHarvester | JSON blob | ❌ |
| holehe | JSONL | ✅ |
| sslscan | XML | ❌ (file-based) |
| paramspider | line | ✅ |
| hakrawler | line | ✅ |
| subzy | JSONL | ✅ |
| crlfuzz | line | ✅ |
| rustscan | line | ✅ |
| netexec | text | ❌ (multi-line) |
| kerbrute | text | ❌ (multi-line) |
| hydra | text | ❌ (multi-line) |
| enum4linux | text | ❌ (multi-line) |
| commix | text | ❌ (multi-line) |
| gowitness | JSON blob | ❌ |
| jwt_tool | text | ❌ (multi-line) |
| name-that-hash | JSON blob | ❌ |
| hashid | text | ❌ (multi-line) |

### Subscribing to Streamed Items

In a `script:` step running concurrently, you can subscribe to live items:

```python
# In a script: step
items = subscribe("task:nmap:items")
for item in items:
    if item["_type"] == "port" and item["port"] == 445:
        publish("smb_found", True)
        break
```

---

## Data Chaining

Task outputs are stored in the registry and accessible via templates. Use the built-in helper functions to filter typed outputs:

### Template Helpers

| Helper | Description |
|--------|-------------|
| `of_type(items, "type")` | Filter items by `_type` field |
| `ports(items)` | Shortcut for `of_type(items, "port")` |
| `urls(items)` | Shortcut for `of_type(items, "url")` |
| `vulns(items)` | Shortcut for `of_type(items, "vulnerability")` |
| `subdomains(items)` | Shortcut for `of_type(items, "subdomain")` |
| `ips(items)` | Shortcut for `of_type(items, "ip")` |
| `tags(items)` | Shortcut for `of_type(items, "tag")` |
| `records(items)` | Shortcut for `of_type(items, "record")` |
| `domains(items)` | Shortcut for `of_type(items, "domain")` |
| `users(items)` | Shortcut for `of_type(items, "user_account")` |

### Example: Chaining Nmap → Httpx

```yaml
name: Recon Pipeline
jobs:
  recon:
    steps:
      - task: nmap
        name: port-scan
        with:
          target: "{{ inputs.target }}"
          ports: "80,443,8080,8443"
          version_detection: true

      - task: httpx
        name: probe-http
        with:
          target: "{{ inputs.target }}"
          tech_detect: true
          status_code: true

      - run: |
          echo "Open ports:"
          echo '{{ ports(steps[0].outputs.typed_outputs) | map(attribute="host_port") | join("\n") }}'
          echo ""
          echo "Live URLs:"
          echo '{{ urls(steps[1].outputs.typed_outputs) | map(attribute="url") | join("\n") }}'
```

### Example: Full Recon Workflow

```yaml
name: Full Recon
jobs:
  subdomain-enum:
    steps:
      - task: subfinder
        name: find-subdomains
        with:
          target: "{{ inputs.domain }}"
          all: true

      - task: dnsx
        name: resolve-dns
        with:
          target: "{{ inputs.domain }}"
          a: true
          cname: true

  vuln-scan:
    needs: [subdomain-enum]
    steps:
      - task: nuclei
        name: scan-vulns
        with:
          target: "{{ inputs.domain }}"
          severity: "critical,high,medium"
          tags: "cve"

      - task: wafw00f
        name: detect-waf
        with:
          target: "https://{{ inputs.domain }}"

      - run: |
          echo "=== Scan Summary ==="
          echo "Vulnerabilities: {{ vulns(steps[0].outputs.typed_outputs) | length }}"
          echo "WAFs detected: {{ tags(steps[1].outputs.typed_outputs) | length }}"
```

---

## Cloud Execution

Tasks work in cloud jobs — the command is built locally and executed on the remote VPS:

```yaml
jobs:
  remote-scan:
    cloud: do-nyc
    steps:
      - task: nmap
        with:
          target: "10.0.0.0/24"
          ports: "1-65535"
          timing: 4
```

The tool must be installed on the remote host. Use the `tools` block or pre-baked images.

---

## Tool Options Reference

### nmap
```yaml
- task: nmap
  with:
    target: "192.168.1.0/24"
    ports: "1-1000"              # -p
    version_detection: true       # -sV
    tcp_syn: true                 # -sS
    os_detect: true               # -O
    scripts: "vuln"               # --script
    timing: 4                     # -T
    top_ports: 100                # --top-ports
    fragment: true                # -f
```

### naabu
```yaml
- task: naabu
  with:
    target: "192.168.1.0/24"
    ports: "80,443,8080"          # -p
    top_ports: "1000"             # -top-ports
    scan_type: "SYN"              # -scan-type
    rate: 1000                    # -rate
    threads: 25                   # -c
    nmap: true                    # -nmap (run nmap on found ports)
```

### httpx
```yaml
- task: httpx
  with:
    target: "example.com"
    tech_detect: true             # -tech-detect
    status_code: true             # -status-code
    title: true                   # -title
    web_server: true              # -web-server
    follow_redirects: true        # -follow-redirects
    threads: 50                   # -threads
    match_code: "200,301"         # -mc
    filter_code: "404"            # -fc
    ports: "80,443,8080"          # -ports
```

### subfinder
```yaml
- task: subfinder
  with:
    target: "example.com"
    all: true                     # -all (use all sources)
    recursive: true               # -recursive
    sources: "shodan,censys"      # -sources
    threads: 30                   # -t
    timeout: 30                   # -timeout
```

### nuclei
```yaml
- task: nuclei
  with:
    target: "https://example.com"
    templates: "cves/"            # -t
    tags: "rce,sqli,xss"         # -tags
    severity: "critical,high"     # -severity
    rate_limit: 150               # -rate-limit
    concurrency: 25               # -concurrency
    headless: true                # -headless
    automatic_scan: true          # -automatic-scan
```

### ffuf
```yaml
- task: ffuf
  with:
    target: "https://example.com/FUZZ"
    wordlist: "/usr/share/seclists/Discovery/Web-Content/common.txt"  # -w
    threads: 50                   # -t
    match_codes: "200,301,302"    # -mc
    filter_codes: "404"           # -fc
    extensions: "php,html,js"     # -e
    follow_redirects: true        # -r
    recursion: true               # -recursion
```

### feroxbuster
```yaml
- task: feroxbuster
  with:
    target: "https://example.com"
    wordlist: "/usr/share/seclists/Discovery/Web-Content/common.txt"  # -w
    threads: 50                   # -t
    depth: 3                      # -d
    extensions: "php,html,js"     # -x
    status_codes: "200,301"       # -s
    filter_status: "404"          # -C
    extract_links: true           # -e
    insecure: true                # -k
```

### katana
```yaml
- task: katana
  with:
    target: "https://example.com"
    depth: 3                      # -depth
    js_crawl: true                # -js-crawl
    headless: true                # -headless
    known_files: "all"            # -known-files
    rate_limit: 150               # -rate-limit
    strategy: "breadth-first"     # -strategy
```

### dnsx
```yaml
- task: dnsx
  with:
    target: "example.com"
    a: true                       # -a (A records)
    aaaa: true                    # -aaaa (AAAA records)
    cname: true                   # -cname
    mx: true                      # -mx
    ns: true                      # -ns
    txt: true                     # -txt
    threads: 100                  # -t
    wildcard: true                # -wildcard
```

### wafw00f
```yaml
- task: wafw00f
  with:
    target: "https://example.com"
    all: true                     # -a (test all WAF signatures)
    proxy: "http://127.0.0.1:8080"  # -p
```

---

## Creating Custom Tasks

You can add your own tool wrappers by subclassing `Task`, implementing `parse_output()`, and registering with `@TaskRegistry.register()`.

### Minimal Example

```python
# src/ofx/tasks/tools/mytool.py
from __future__ import annotations

import json
from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Url
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("mytool")
class MyToolTask(Task):
    name = "mytool"
    cmd = "mytool"
    description = "My custom HTTP scanner"
    category = "url/scan"
    install_cmd = "go install github.com/example/mytool@latest"
    output_types = [Url]

    opts = {
        "threads": OptDef(flag="-t", type=int, help="Number of threads"),
        "timeout": OptDef(flag="--timeout", type=int, help="Timeout per request"),
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose output"),
    }

    input_flag = "-u"        # how target is passed
    file_flag = "-l"         # flag for target list file
    output_flag = "-o"       # flag for output file
    extra_flags = ["-json"]  # always appended

    def _output_suffix(self) -> str:
        return ".jsonl"

    def parse_output(
        self, stdout: str, stderr: str, output_file: Path | None = None
    ) -> list[Url]:
        results: list[Url] = []
        lines = []

        if output_file and output_file.exists():
            lines = self._read_output_file(output_file).strip().splitlines()
        elif stdout:
            lines = stdout.strip().splitlines()

        for line in lines:
            results.extend(self.parse_line(line))
        return results

    def parse_line(self, line: str) -> list[Url]:
        """Parse a single JSONL line (enables live streaming)."""
        line = line.strip()
        if not line or not line.startswith("{"):
            return []
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return []

        url = data.get("url", "")
        if not url:
            return []

        return [Url(
            url=url,
            host=data.get("host", ""),
            status_code=self._safe_int(data.get("status_code", 0)),
            title=data.get("title", ""),
        )]
```

### Key Points

| Attribute | Purpose |
|-----------|---------|
| `name` | Registry key and display name |
| `cmd` | Binary name (checked with `shutil.which`) |
| `category` | Grouping for `ofx flow tasks list -c` |
| `opts` | Maps Python kwargs to CLI flags via `OptDef` |
| `input_flag` | How the target is passed (`None` = positional) |
| `file_flag` | Flag for target list files (`-l`, `-iL`, etc.) |
| `output_flag` | Flag for structured output file |
| `extra_flags` | Always appended (e.g. `-json`, `-silent`) |
| `output_types` | List of output type classes this tool produces |
| `install_cmd` | Shown when binary is missing |

### Adding Streaming Support

To enable live streaming, implement `parse_line()` — the base class auto-detects it:

```python
def parse_line(self, line: str) -> list[OutputType]:
    """Parse one stdout line into items. Return [] for unparseable lines."""
    ...
```

Tools that output JSONL or one-result-per-line are ideal candidates. XML/multi-line tools should only implement `parse_output()`.

### Using in Workflows

```yaml
steps:
  - task: mytool
    with:
      target: "{{ inputs.target }}"
      threads: 20
      verbose: true
```

The task is automatically discovered if placed in `src/ofx/tasks/tools/`.

---

## Profile Integration

When a profile is active (via `defaults.profile` in a workflow or `--profile` on the CLI), OFX automatically maps profile-level settings to matching task options. This means you don't need to manually pass `threads`, `proxy`, or `rate_limit` to every task — the profile handles it.

### Automatic Mapping

| Profile Field | Mapped Task Opts (first match wins) |
|--------------|-------------------------------------|
| `proxy` | `proxy`, `proxy_url`, `http_proxy` |
| `threads` | `threads`, `concurrency`, `workers` |
| `rate_limit` | `rate_limit`, `rate` |
| `delay` | `delay` |
| `user_agent` | `user_agent` |

**How it works:**

1. For each profile field with a non-zero/non-empty value, OFX checks if the task declares a matching opt name
2. If a match is found and the user hasn't explicitly set that opt, the profile value is injected
3. Explicit user options (from `with:` in YAML or `--opt` on CLI) always take precedence

**Example:** A profile with `threads: 5` and `proxy: socks5://127.0.0.1:9050` will automatically set those options on any task that declares `threads` and `proxy` opts — which includes httpx, nuclei, naabu, ffuf, subfinder, and many more.

### Per-Task Overrides

For fine-grained control, use `task_options` in the profile to override specific tools:

```yaml
profiles:
  stealth:
    threads: 2          # auto-injected into all tasks with a "threads" opt
    rate_limit: 30      # auto-injected into all tasks with a "rate_limit" opt
    proxy: "socks5://127.0.0.1:9050"
    task_options:
      nmap:
        timing: "T2"    # nmap-specific override
      nuclei:
        rate_limit: 10  # override the global rate_limit for nuclei only
```

See [Profiles](profiles.md) for full documentation.

---

## See Also

- [Steps](jobs-steps/steps.md)
- [Workflows](workflows.md)
- [Profiles](profiles.md)
- [Cloud Execution](cloud-runners.md)
- [CLI Reference: Tasks](../cli/commands/tasks.md)
