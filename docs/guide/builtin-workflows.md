# Built-in Workflows

OFX ships with **27 built-in workflows** inspired by [secator](https://github.com/freelabz/secator)'s scan and workflow system. These leverage OFX's [task system](tasks.md) with structured output types and data chaining between steps.

---

## Workflow Categories

### Setup

| Workflow | Description |
|----------|-------------|
| `cloud-setup` | Provision cloud VPS with Go, Ruby, uv, and all 42 security tools |

### Reconnaissance

| Workflow | Description | Tools |
|----------|-------------|-------|
| `domain-recon` | Domain info: WHOIS, DNS, HTTP, TLS, WAF | whois, dnsx, httpx, testssl, wafw00f |
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

### Red Team

| Workflow | Description | Tools |
|----------|-------------|-------|
| `external-recon` | Comprehensive external recon pipeline (11 jobs) covering subdomain enum, DNS, port scanning, web probing, crawling, fuzzing, parameter discovery, vulnerability scanning, SSL audit, and OSINT | subfinder, amass, assetfinder, findomain, dnsx, dnsrecon, naabu, masscan, nmap, httpx, whatweb, wafw00f, katana, gospider, cariddi, gau, ffuf, gobuster, arjun, x8, nuclei, dalfox, sslscan, testssl, theHarvester, h8mail |

### Comprehensive Scans

Multi-phase assessments with data chaining between jobs:

| Scan | Phases |
|------|--------|
| `domain-scan` | Domain recon → Subdomain discovery → Host recon → URL crawling → Vuln scan |
| `host-scan` | Port scan → Service detection → SSH audit → URL crawling → Vuln scan |
| `network-scan` | Host discovery → Service detection → URL crawling → Vuln scan |
| `subdomain-scan` | Subdomain enum → Host recon → URL crawling → Vuln scan |
| `url-scan` | URL crawling → Dir fuzzing → Param discovery → Vuln scan |
| `full-recon` | Full recon pipeline (8 jobs) — subdomain enum, DNS resolution, port scanning, web probing, crawling, directory fuzzing, vulnerability scanning, reporting |

---

## Usage

### Running Workflows

```bash
# Run a built-in workflow
uv run ofx flow run domain-recon --input target=example.com

# Run a comprehensive scan
uv run ofx flow run domain-scan --input target=example.com

# Run with output directory
uv run ofx flow run host-scan --input target=10.10.10.10 -o ./results/
```

### Cloud Execution

```bash
# 1. Set up cloud profile
uv run ofx cloud profile add do-nyc \
  --provider digitalocean --region nyc3 \
  --size s-2vcpu-4gb --image ubuntu-24-04-x64 \
  --ssh-key ~/.ssh/id_ed25519

# 2. Provision VPS with all tools
uv run ofx flow run cloud-setup --cloud do-nyc

# 3. Run scans on cloud
uv run ofx flow run domain-scan --input target=example.com --cloud do-nyc
```

### With Profiles

```bash
# Create an opsec profile
uv run ofx flow profile add stealthy \
  --rate-limit 10 --delay 2 --jitter 1 \
  --time-window '{"start": "09:00", "end": "17:00"}'

# Run with profile
uv run ofx flow run subdomain-recon --input target=example.com --profile stealthy
```

---

## Cloud Setup

The `cloud-setup` workflow installs all 42 tools on a fresh VPS with parallel installation:

```
setup-runtime ──┬── install-apt-tools    (nmap, whois, exploitdb, nikto, whatweb, sslscan, fping, masscan)
                ├── install-go-tools     (16 Go tools incl. gobuster, amass, assetfinder, mapcidr, cariddi)
                ├── install-python-tools (9 Python tools via uv incl. sqlmap, dnsrecon, theHarvester, holehe)
                ├── install-rust-tools   (x8, feroxbuster)
                └── install-other-tools  (grype, trivy, testssl, wpscan, findomain)
                         │
                     verify  (checks all 42 tools)
```

```bash
uv run ofx flow run cloud-setup --cloud do-nyc
uv run ofx flow run cloud-setup --cloud do-nyc --input skip_apt=true
```

---

## Secator Equivalence

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

### Key Advantages over Secator

- **YAML workflows** — fully customizable, version-controllable
- **Cloud-native execution** — built-in VPS provisioning
- **Fleet distribution** — split targets across multiple VPS instances
- **Matrix strategies** — run tool variations in parallel
- **Profile system** — rate limiting, time windows, opsec controls
- **Data chaining via templates** — Jinja2 expressions for typed output routing
