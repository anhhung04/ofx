# Built-in Workflows

OFX ships with over **170 built-in workflows** organized across six categories:
setup, reconnaissance, web security, code security, exploitation, and network
infrastructure. Workflows leverage OFX's [task system](tasks.md) with structured
output types and data chaining between steps.

---

## Workflow Categories

### Setup (7 workflows)

| Workflow | Description |
|----------|-------------|
| `cloud-setup` | Provision cloud VPS with Go, Ruby, uv, and 56 security tools |
| `pentest-env` | Bootstrap a penetration testing workstation with tools, wordlists, and shell config |
| `c2-redirector` | Set up an authorized C2 redirector with Nginx reverse proxying and SSL termination |
| `exfil-channels` | Configure multiple data exfiltration channels (HTTPS, DNS, ICMP) |
| `docker-lab` | Spin up disposable Docker Compose security labs (DVWA, Juice Shop, etc.) |
| `proxy-config` | Configure proxychains, TOR, SSH tunnels, and VPN routing |
| `git-secrets-guard` | Set up pre-commit secret scanning hooks with CI integration |

### Reconnaissance (11 workflows)

| Workflow | Description |
|----------|-------------|
| `subdomain-enum` | Passive and active subdomain discovery via multiple sources |
| `dns-resolve` | DNS resolution and record validation |
| `http-probe` | HTTP/HTTPS service probing and screenshot capture |
| `port-scan` | Network port scanning with configurable scanners |
| `service-enum` | Service version detection and enumeration |
| `content-discovery` | Hidden file and directory discovery |
| `vuln-scan` | Comprehensive vulnerability scanning |
| `js-analysis` | JavaScript endpoint and secret extraction |
| `osint-gather` | Open source intelligence collection |
| `data-aggregate` | Aggregate and report on all collected data |
| `full-recon` | Master pipeline chaining all recon modules |

### Web Security (26 workflows)

| Workflow | Description |
|----------|-------------|
| `web-full-audit` | Comprehensive web application audit (ports, fingerprinting, vulns, secrets) |
| `web-fingerprint` | Web technology fingerprinting and WAF detection |
| `sqli-scan` | SQL injection scanning and exploitation |
| `ssrf-scan` | Server-Side Request Forgery scanner |
| `ssti-scan` | Server-Side Template Injection testing |
| `command-injection` | OS command injection testing |
| `xxe-scan` | XML External Entity injection testing |
| `nosql-injection` | NoSQL injection testing (MongoDB, Redis, etc.) |
| `nikto-scan` | Web server vulnerability scanning |
| `cors-scan` | CORS misconfiguration scanner |
| `header-audit` | HTTP security header audit and grading |
| `request-smuggling` | HTTP request smuggling detection |
| `cache-poison` | Web cache poisoning detection |
| `jwt-audit` | JWT security audit |
| `oob-inject` | Out-of-band injection tester with Interactsh |
| `api-fuzz` | REST API endpoint fuzzing (IDOR, auth bypass) |
| `api-security-audit` | Comprehensive API security audit (GraphQL, OpenAPI) |
| `graphql-audit` | GraphQL API security audit |
| `url-crawl` | Active URL crawling with passive source enrichment |
| `url-fuzz` | Directory brute-forcing with intelligent calibration |
| `url-dirsearch` | Directory/file discovery with dirsearch |
| `url-params-fuzz` | Parameter fuzzing for hidden parameters |
| `url-secrets-hunt` | Secret detection in web responses |
| `url-vuln` | URL-level vulnerability scanning |
| `js-analysis` | JavaScript endpoint and secret extraction |
| `wordpress` | WordPress-specific vulnerability assessment |

### Code Security (4 workflows)

| Workflow | Description |
|----------|-------------|
| `code-scan` | SAST + dependency scanning + secret detection |
| `secrets-hunt` | Deep secret and credential scanning in repos |
| `dependency-audit` | Dependency vulnerability audit across ecosystems |
| `container-scan` | Container image vulnerability and Dockerfile analysis |

### Exploitation (56 workflows)

Active Directory attacks, credential harvesting, lateral movement, privilege
escalation, payload generation, C2 operations, and operational security.

**AD Attacks:** `ad-attack`, `ad-enum`, `ad-dump-creds`, `ad-certattack`, `ad-certattack-task`, `ad-kerberoast-task`, `ad-recon-api`, `kerberoast`, `bloodhound-collect`, `ntlm-relay`, `coerce-scan`, `password-spray`, `password-audit`

**Post-Exploitation:** `post-exploit`, `credential-hunt`, `lateral-movement`, `internal-recon`, `opsec-cleanup`, `network-tunnel`

**Privilege Escalation:** `privesc-audit`, `privesc-check`, `privesc-linux`, `privesc-windows`, `exploit-to-persist`

**Payload Generation:** `payload-gen`, `payload-encode`, `payload-pack`, `revshell-gen`, `email-gen`, `persistence-gen`

**C2 & Infrastructure:** `c2-shells`, `webshell-ops`, `proxy-setup`, `phishing-infra`

**Exfiltration:** `exfil-decode`, `exfil-prep`

**Credential Attacks:** `hash-crack`, `jwt-analyze`

**Reconnaissance Utilities:** `external-recon`, `dns-enum`, `http-probe`, `file-analyze`, `extract-iocs`, `yara-scan`

**Utility Workflows:** `collect-ports`, `collect-subdomains`, `collect-urls`, `defang-refang`, `diff-hosts`, `encode-decode`, `export-results`, `ip-tools`, `log-analyzer`, `oob-test`, `parse-targets`, `traffic-blend`

### Network & Infrastructure (66 workflows)

Comprehensive network reconnaissance, OSINT gathering, cloud/DevOps auditing,
and full penetration testing pipelines.

**Domain Recon:** `domain-recon`, `domain-scan`, `domain-whois-bulk`, `domain-permutations`, `dns-history`, `crtsh-enum`, `subdomain`, `subdomain-recon`, `subdomain-scan`, `subdomain-takeover`, `recursive-domain-scan`, `takeover-scan`

**Host & Network:** `host-recon`, `host-scan`, `network-discovery`, `network-scan`, `network-sweep`, `cidr-recon`, `port-scan`, `port-blitz`, `banner-grab`, `service-enum`

**Web Recon:** `url-scan`, `url-discovery`, `web-probe`, `api-endpoints`, `vhost-discovery`, `backup-files`

**Cloud & DevOps:** `cloud-enum`, `cloud-security-audit`, `cloud-aws-audit`, `k8s-audit`, `cicd-audit`, `s3-buckets`, `docker-registry-enum`, `firebase-check`

**OSINT:** `osint`, `company-recon`, `email-osint`, `user-hunt`, `asn-recon`, `shodan-recon`, `fofa-search`, `open-databases`, `phone-osint`, `smtp-enum`, `snmp-enum`

**Vulnerability:** `vuln-sweep`, `vuln-prioritize`, `ssl-audit`, `ssl-deep`, `security-headers`, `secret-scan`, `supply-chain`, `container-scan`, `linux-hardening`, `llm-security-audit`, `ad-discovery`, `ldap-enum`

**Pipelines:** `full-recon`, `deep-recon`, `quick-recon`, `bug-bounty-recon`, `pentest-external`, `target-profiling`

**Utilities:** `target-file`, `gogo-zombie`

### Finding Workflows

```bash
# List all built-in workflows
ofx flow list --builtin

# Search by name or keyword
ofx flow search "domain"      # Find domain-related workflows
ofx flow search "sqli"        # Find SQL injection workflows
ofx flow search "ad"          # Find Active Directory workflows

# Filter by tags
ofx flow search --tags redteam
ofx flow search --tags cloud
```

---

## Usage

### Running Workflows

```bash
# Run a built-in workflow
ofx flow run domain-recon --input target=example.com

# Run a comprehensive scan
ofx flow run domain-scan --input target=example.com

# Run an exploitation workflow
ofx flow run ad-enum --input target=dc01.corp.local --input domain=corp.local

# Run with cloud execution
ofx flow run full-recon --input target=example.com --cloud do-nyc

# Run with a stealth profile
ofx flow run subdomain-recon --input target=example.com --profile stealthy
```

### Runtime Logging Inputs

Built-in workflows expose two common runtime inputs for controlling output verbosity:

| Input | Default | Effect |
|-------|---------|--------|
| `log_command` | `true` | Controls step `log-command` entries |
| `log_output` | `true` | Controls step `log-stdout` output capture |

```bash
# Quiet mode for recursive workflows
ofx flow run recursive-domain-scan \
  --input target=example.com \
  --input log_command=false \
  --input log_output=false
```

### Running Individual Tasks

```bash
ofx flow tasks run nmap 10.10.10.5 --opt ports=1-1000 --opt timing=T4
ofx flow tasks run httpx targets.txt --opt threads=50
ofx flow tasks run nuclei https://example.com --profile stealth
```

---

## Cloud Setup

The `cloud-setup` workflow installs all 56+ tools on a fresh VPS:

```
setup-runtime ──┬── install-apt-tools    (nmap, whois, exploitdb, nikto, whatweb, sslscan, fping, masscan)
                ├── install-go-tools     (16 Go tools incl. gobuster, amass, assetfinder, mapcidr)
                ├── install-python-tools (9 Python tools via uv incl. sqlmap, dnsrecon, theHarvester)
                ├── install-rust-tools   (x8, feroxbuster)
                └── install-other-tools  (grype, trivy, testssl, wpscan, findomain)
                         │
                     verify  (checks all installed tools)
```

```bash
ofx flow run cloud-setup --cloud do-nyc
ofx flow run pentest-env   # Workstation setup for local use
```

---

## Collection Manifests

Each workflow category includes a `collection.yaml` manifest used by the OFX
search and listing commands. Individual README files provide usage examples
and tool requirements:

| Category | Path | Workflows |
|----------|------|-----------|
| Setup | `src/ofx/data/workflows/setup/` | 7 |
| Reconnaissance | `src/ofx/data/workflows/recon/` | 11 |
| Web Security | `src/ofx/data/workflows/web/` | 26 |
| Code Security | `src/ofx/data/workflows/code/` | 4 |
| Exploitation | `src/ofx/data/workflows/exploit/` | 56 |
| Network & Infrastructure | `src/ofx/data/workflows/network/` | 66 |

---

## Key Advantages over Secator

- **YAML workflows** — fully customizable, version-controllable
- **Cloud-native execution** — built-in VPS provisioning
- **Fleet distribution** — split targets across multiple VPS instances
- **Matrix strategies** — run tool variations in parallel
- **Profile system** — rate limiting, time windows, opsec controls
- **Data chaining via templates** — Jinja2 expressions for typed output routing
- **169 built-in workflows** — comprehensive coverage of the full assessment lifecycle
