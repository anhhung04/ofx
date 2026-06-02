# Built-in Workflows

OFX ships with **35 built-in workflows** inspired by [secator](https://github.com/freelabz/secator)'s scan and workflow system. These leverage OFX's [task system](tasks.md) with structured output types and data chaining between steps.

---

## Workflow Categories

### Setup

| Workflow | Description |
|----------|-------------|
| `cloud-setup` | Provision cloud VPS with Go, Ruby, uv, and all 56 security tools |

### Reconnaissance

| Workflow | Description | Tools |
|----------|-------------|-------|
| `domain-recon` | Full domain recon: WHOIS, DNS, subdomains, HTTP, TLS, WAF, crawling, vulns | whois, dnsx, dnsrecon, subfinder, amass, assetfinder, gau, httpx, testssl, sslscan, tlsx, cdncheck, wafw00f, whatweb, katana, gospider, naabu, nmap, nuclei, dalfox, nikto, subzy, dnstake |
| `host-recon` | Port discovery, service detection, SSH audit, vulns | naabu, nmap, ssh-audit, httpx, searchsploit, nuclei |
| `subdomain-recon` | Passive enum, DNS verification, takeover check | subfinder, amass, assetfinder, gau, dnsx, httpx, nuclei |
| `cidr-recon` | CIDR host discovery, port scan, service detection | nmap, naabu, httpx, searchsploit |
| `network-discovery` | Network host discovery and service fingerprinting | fping, masscan, naabu, nmap, httpx |

### Web Security

| Workflow | Description | Tools |
|----------|-------------|-------|
| `url-crawl` | Active crawling + passive sources + probing | katana, gospider, cariddi, gau, httpx, trufflehog |
| `url-fuzz` | Directory fuzzing with intelligent calibration | ffuf, gobuster, feroxbuster, httpx, trufflehog |
| `url-dirsearch` | Directory/file discovery + content crawling | dirsearch, ffuf, katana, httpx |
| `url-vuln` | XSS and vulnerability scanning | dalfox, nuclei |
| `url-params-fuzz` | Parameter discovery and value fuzzing | arjun, x8, ffuf, httpx |
| `url-secrets-hunt` | Secret detection in HTTP responses | httpx, trufflehog |
| `url-fingerprint` | Web server fingerprinting and WAF detection | httpx, whatweb, wafw00f |
| `sqli-scan` | SQL injection scanning and exploitation | sqlmap |
| `nikto-scan` | Web server scanning and vulnerability detection | nikto, nuclei |
| `wordpress` | WordPress vulnerability assessment | wpscan, nuclei, httpx |
| `command-injection` | Command injection testing | commix, nuclei |
| `jwt-audit` | JWT security audit | jwt_tool |

### Code Security & OSINT

| Workflow | Description | Tools |
|----------|-------------|-------|
| `code-scan` | Dependency vulns + secret/leak detection | grype, trivy, gitleaks, trufflehog |
| `user-hunt` | Username hunting + email breach search | maigret, h8mail |
| `email-osint` | Email OSINT — harvesting, breach lookup, account enumeration | theHarvester, h8mail, holehe |

### Scans

| Workflow | Description | Tools |
|----------|-------------|-------|
| `ssl-audit` | SSL/TLS certificate and cipher audit | sslscan, testssl |
| `bug-bounty-recon` | 10-job bug bounty recon pipeline | subfinder, amass, dnsx, naabu, httpx, katana, paramspider, hakrawler, nuclei, dalfox, subzy |
| `takeover-scan` | Subdomain takeover scanning | subzy, nuclei |
| `pentest-external` | 12-job external pentest methodology | subfinder, dnsx, naabu, rustscan, nmap, httpx, gowitness, ffuf, nuclei, dalfox, crlfuzz, commix, sslscan, testssl |

### Red Team

| Workflow | Description | Tools |
|----------|-------------|-------|
| `external-recon` | Comprehensive external recon pipeline (11 jobs) covering subdomain enum, DNS, port scanning, web probing, crawling, fuzzing, parameter discovery, vulnerability scanning, SSL audit, and OSINT | subfinder, amass, assetfinder, findomain, dnsx, dnsrecon, naabu, masscan, rustscan, nmap, httpx, whatweb, wafw00f, katana, gospider, hakrawler, cariddi, gau, paramspider, ffuf, gobuster, arjun, x8, nuclei, dalfox, subzy, crlfuzz, sslscan, testssl, gowitness, theHarvester, h8mail |
| `ad-enum` | AD enumeration via SMB/Kerberos/LDAP | netexec, enum4linux, kerbrute |
| `password-spray` | Password spraying with Kerberos and SMB | netexec, kerbrute |
| `internal-recon` | Internal network recon pipeline | fping, rustscan, nmap, netexec, gowitness |

### Comprehensive Scans

Multi-phase assessments with data chaining between jobs:

| Scan | Phases |
|------|--------|
| `domain-scan` | Domain recon → Subdomain discovery → Host recon → URL crawling → Vuln scan |
| `host-scan` | Port scan → Service detection → SSH audit → URL crawling → Vuln scan |
| `network-scan` | Host discovery → Service detection → URL crawling → Vuln scan |
| `subdomain-scan` | Subdomain enum → Host recon → URL crawling → Vuln scan |
| `url-scan` | URL crawling → Dir fuzzing → Param discovery → Vuln scan |
| `full-recon` | Full recon pipeline (8 jobs) — subdomain enum, DNS resolution, port scanning, web probing, crawling, directory fuzzing, vulnerability scanning, reporting | subfinder, amass, dnsx, naabu, rustscan, nmap, httpx, gowitness, katana, gospider, hakrawler, ffuf, gobuster, nuclei, dalfox, subzy |

---

## Usage

### Running Workflows

```bash
# Run a built-in workflow
ofx flow run domain-recon --input target=example.com

# Run a comprehensive scan
ofx flow run domain-scan --input target=example.com

# Run with output directory
ofx flow run host-scan --input target=10.10.10.10 -o ./results/

# Disable command log entries but keep stdout artifact logs
ofx flow run full-recon \
  --input target=example.com \
  --input log_command=false \
  --input log_output=true
```

### Runtime Logging Inputs

Built-in workflows now expose two common runtime inputs:

| Input | Default | Effect |
|-------|---------|--------|
| `log_command` | `true` | Controls step `log-command` entries |
| `log_output` | `true` | Controls step `log-stdout` output capture |

These inputs are read by the builtin workflow YAML itself, so you can change logging behavior per run without editing the workflow file.

For builtin workflows that call other builtin workflows with `uses:`, the same inputs continue to apply recursively because subworkflows inherit the parent run inputs.

```bash
# Quiet down recursive builtin workflows for one run
ofx flow run recursive-domain-scan \
  --input target=example.com \
  --input log_command=false \
  --input log_output=false
```

### Running Individual Tasks

Run any registered task directly without a workflow file:

```bash
# Quick port scan
ofx flow tasks run nmap 10.10.10.5 --opt ports=1-1000 --opt timing=T4

# HTTP probing
ofx flow tasks run httpx targets.txt --opt threads=50

# Vulnerability scan with stealth profile
ofx flow tasks run nuclei https://example.com --profile stealth
```

See [Tasks CLI Reference](../cli/commands/tasks.md) for full options.

### Cloud Execution

```bash
# 1. Set up cloud profile
ofx cloud profile add do-nyc \
  --provider digitalocean --region nyc3 \
  --size s-2vcpu-4gb --image ubuntu-24-04-x64 \
  --ssh-key ~/.ssh/id_ed25519

# 2. Provision VPS with all tools
ofx flow run cloud-setup --cloud do-nyc

# 3. Run scans on cloud
ofx flow run domain-scan --input target=example.com --cloud do-nyc
```

### With Profiles

```bash
# Create an opsec profile
ofx flow profile add stealthy \
  --rate-limit 10 --delay 2 --jitter 1 \
  --time-window '{"start": "09:00", "end": "17:00"}'

# Run with profile
ofx flow run subdomain-recon --input target=example.com --profile stealthy
```

---

## Cloud Setup

The `cloud-setup` workflow installs all 56 tools on a fresh VPS with parallel installation:

```
setup-runtime ──┬── install-apt-tools    (nmap, whois, exploitdb, nikto, whatweb, sslscan, fping, masscan)
                ├── install-go-tools     (16 Go tools incl. gobuster, amass, assetfinder, mapcidr, cariddi)
                ├── install-python-tools (9 Python tools via uv incl. sqlmap, dnsrecon, theHarvester, holehe)
                ├── install-rust-tools   (x8, feroxbuster)
                └── install-other-tools  (grype, trivy, testssl, wpscan, findomain)
                         │
                     verify  (checks all 56 tools)
```

```bash
ofx flow run cloud-setup --cloud do-nyc
ofx flow run cloud-setup --cloud do-nyc --input skip_apt=true
```

---

## Secator Equivalence

### Workflows

| Secator Command | OFX Equivalent |
|----------------|----------------|
| `secator w domain_recon` | `ofx flow run domain-recon` |
| `secator w host_recon` | `ofx flow run host-recon` |
| `secator w subdomain_recon` | `ofx flow run subdomain-recon` |
| `secator w url_crawl` | `ofx flow run url-crawl` |
| `secator w url_fuzz` | `ofx flow run url-fuzz` |
| `secator w url_dirsearch` | `ofx flow run url-dirsearch` |
| `secator w url_vuln` | `ofx flow run url-vuln` |
| `secator w url_params_fuzz` | `ofx flow run url-params-fuzz` |
| `secator w url_secrets_hunt` | `ofx flow run url-secrets-hunt` |
| `secator w code_scan` | `ofx flow run code-scan` |
| `secator w user_hunt` | `ofx flow run user-hunt` |
| `secator w wordpress` | `ofx flow run wordpress` |
| `secator s domain` | `ofx flow run domain-scan` |
| `secator s host` | `ofx flow run host-scan` |
| `secator s network` | `ofx flow run network-scan` |
| `secator s subdomain` | `ofx flow run subdomain-scan` |
| `secator s url` | `ofx flow run url-scan` |
| — | `ofx flow run network-discovery` |
| — | `ofx flow run email-osint` |
| — | `ofx flow run url-fingerprint` |
| — | `ofx flow run sqli-scan` |
| — | `ofx flow run nikto-scan` |
| — | `ofx flow run ssl-audit` |
| — | `ofx flow run full-recon` |
| — | `ofx flow run external-recon` |
| — | `ofx flow run ad-enum` |
| — | `ofx flow run password-spray` |
| — | `ofx flow run internal-recon` |
| — | `ofx flow run command-injection` |
| — | `ofx flow run jwt-audit` |
| — | `ofx flow run bug-bounty-recon` |
| — | `ofx flow run takeover-scan` |
| — | `ofx flow run pentest-external` |

### Individual Tasks

| Secator Command | OFX Equivalent |
|----------------|----------------|
| `secator x nmap <target>` | `ofx flow tasks run nmap <target>` |
| `secator x httpx <target>` | `ofx flow tasks run httpx <target>` |
| `secator x nuclei <target>` | `ofx flow tasks run nuclei <target>` |
| `secator x subfinder <target>` | `ofx flow tasks run subfinder <target>` |
| `secator x ffuf <target>` | `ofx flow tasks run ffuf <target>` |
| `secator x <tool> <target> -opt val` | `ofx flow tasks run <tool> <target> --opt opt=val` |

### Key Advantages over Secator

- **YAML workflows** — fully customizable, version-controllable
- **Cloud-native execution** — built-in VPS provisioning
- **Fleet distribution** — split targets across multiple VPS instances
- **Matrix strategies** — run tool variations in parallel
- **Profile system** — rate limiting, time windows, opsec controls
- **Data chaining via templates** — Jinja2 expressions for typed output routing
