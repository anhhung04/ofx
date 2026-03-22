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

### Built-in Tasks

| Task | Category | Description | Output Types |
|------|----------|-------------|-------------|
| `nmap` | port/scan | Network port scanner and service detector | Port, Vulnerability |
| `naabu` | port/scan | Fast port scanner written in Go | Port |
| `httpx` | url/probe | Fast and multi-purpose HTTP toolkit | Url, Tag |
| `ffuf` | url/fuzz | Fast web fuzzer written in Go | Url |
| `feroxbuster` | url/fuzz | Fast content discovery tool written in Rust | Url |
| `katana` | url/crawl | Next-generation crawling and spidering framework | Url |
| `subfinder` | dns/recon | Fast passive subdomain enumeration tool | Subdomain |
| `dnsx` | dns/resolve | Fast and multi-purpose DNS toolkit | Subdomain, Ip, Record |
| `nuclei` | vuln/scan | Fast template-based vulnerability scanner | Vulnerability, Tag |
| `wafw00f` | waf/detect | Web Application Firewall detection tool | Tag |

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
| nmap | XML | ❌ (file-based) |
| ffuf | JSON | ❌ (single blob) |
| wafw00f | stdout | ❌ (multi-line) |

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

## See Also

- [Steps](jobs-steps/steps.md)
- [Workflows](workflows/index.md)
- [Cloud Execution](cloud/index.md)
