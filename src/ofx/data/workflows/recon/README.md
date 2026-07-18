# Reconnaissance Workflow Collection

A modular, comprehensive set of reconnaissance workflows for offensive security assessments. Built for the OFX (Offensive Flow Executor) framework.

## Overview

This collection provides standalone workflows for each phase of reconnaissance, allowing you to run individual modules or chain them together using the `full-recon` master workflow.

### Workflows

#### Core Enumeration

- **subdomain-enum** - Discovers subdomains using multiple passive sources (subfinder, assetfinder, findomain, amass, crtsh) and active bruteforcing (puredns). Deduplicates and validates all findings.
- **dns-resolve** - Resolves subdomains to IP addresses, validates DNS records, and detects potential subdomain takeover vulnerabilities.
- **http-probe** - Identifies live HTTP/HTTPS services, fingerprints technologies, detects WAFs, and captures screenshots.

#### Network Reconnaissance

- **port-scan** - Scans for open ports using configurable scanners (nmap, naabu, masscan, rustscan) with support for various port ranges.
- **service-enum** - Performs service version detection and enumeration using nmap NSE scripts.

#### Web Application Reconnaissance

- **content-discovery** - Discovers hidden files and directories using dirsearch, ffuf, and feroxbuster with parallel execution.
- **vuln-scan** - Runs comprehensive vulnerability scanning with nuclei (web vulns, subdomain takeover, exposures) and specialized tools (dalfox, sqlmap, crlfuzz, subzy).
- **js-analysis** - Analyzes JavaScript files to extract endpoints, API routes, hardcoded secrets, and sensitive data using jsluice.

#### Open Source Intelligence

- **osint-gather** - Collects emails, breach data, domain registration information, GitHub repositories, and other publicly available intelligence using theHarvester, h8mail, whois, dnsrecon, and cariddi.

#### Aggregation

- **data-aggregate** - Scans a project directory and generates a comprehensive summary report with statistics across all collected data.
- **full-recon** - Master workflow that orchestrates all modules in the correct dependency order.

## Installation

If this collection is bundled with OFX, workflows are available immediately. Otherwise, install from a git repository:

```bash
ofx collection add https://github.com/your-org/ofx-recon-collection.git
```

## Usage

### Individual Workflows

Each workflow can be run standalone:

```bash
# Subdomain enumeration
ofx flow run subdomain-enum --input target=example.com

# HTTP probing (with a file of targets)
ofx flow run http-probe --input target=subdomains.txt

# Port scanning
ofx flow run port-scan --input targets=ips.txt --input ports=1-65535

# OSINT gathering
ofx flow run osint-gather --input target=example.com --input email_domain=example.com
```

### Full Reconnaissance

The `full-recon` workflow automates the entire process:

```bash
# Create a project to store results
ofx project init pentest-2024

# Run full reconnaissance
ofx flow run full-recon \
  --input target=example.com \
  --input ports=top-1000 \
  --project pentest-2024
```

Results will be organized in `~/.ofx/projects/pentest-2024/`:

```
pentest-2024/
├── osint/
│   ├── emails.txt
│   ├── breaches.json
│   ├── github_findings.json
│   └── domain_intel.json
├── subdomains/
│   ├── all.txt
│   └── all.json
├── dns/
│   ├── dns_records.txt
│   └── ips.txt
├── ports/
│   └── open_ports.txt
├── services/
│   └── services.txt
├── web/
│   ├── live_urls.txt
│   ├── discovered_paths.txt
├── vulnerabilities/
│   ├── all_vulns.json
│   ├── web_vulns.json
│   ├── takeovers.json
│   └── exposures.json
├── javascript/
│   ├── findings.json
│   ├── endpoints.txt
│   └── secrets.txt
└── aggregate_report.json
```

## Workflow Inputs

### Common Inputs

All workflows accept these common inputs:

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `target` | string | (required) | Target domain, IP, CIDR range, or file path |
| `log_command` | string | "true" | Enable command logging |
| `log_output` | string | "true" | Enable stdout output logs |

### Workflow-Specific Inputs

See individual workflow YAML files for complete input definitions. Key inputs include:

- **subdomain-enum**: `wordlist`, `bruteforce`
- **port-scan**: `ports`, `scanner`, `rate`, `threads`
- **http-probe**: `ports`, `threads`
- **content-discovery**: `wordlist`, `extensions`, `recursive`, `threads`
- **vuln-scan**: `severity`, `tags`, `exclude_tags`, `rate_limit`
- **osint-gather**: `email_domain`, `max_docs`

## Outputs

Each workflow exports structured outputs (typed_outputs) that can be consumed by downstream workflows or the project system. Common output types include:

- `Subdomain` - Discovered subdomains with source metadata
- `Url` - Live web services with status codes and titles
- `Port` - Open ports with service information
- `Ip` - Resolved IP addresses
- `Vulnerability` - Security findings with severity and details
- `UserAccount` - Email addresses and breach data
- `Certificate` - SSL/TLS certificate information

## Customization

### Adjusting Scope

- **Port scanning**: Modify the `ports` input to control scan intensity (e.g., `top-100`, `top-1000`, `1-65535`, or specific ports like `80,443,8080`)
- **Subdomain bruteforce**: Provide a custom wordlist with `--input wordlist=/path/to/wordlist.txt`
- **Content discovery**: Adjust `extensions` and `threads` for performance
- **Vulnerability scanning**: Filter by severity (`--input severity=critical,high`) or tags (`--input tags=xss,sqli`)

### Parallelism

Many workflows use parallel execution at the step or matrix level. Adjust thread/rate limits based on target scope and network capacity to avoid overwhelming targets or triggering rate limits.

## Requirements

Ensure required tools are installed. OFX can auto-install most using the `tools:` section in workflows:

```yaml
tools:
  subfinder:
    install: go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
    check: subfinder -version
```

Common tools used:

- subfinder, assetfinder, findomain, amass, puredns
- httpx, whatweb, wafw00f, gowitness
- nmap, naabu, masscan, dnsx, dnstake
- dirsearch, ffuf, feroxbuster, katana
- nuclei, dalfox, sqlmap, subzy
- theHarvester, h8mail, whois, dnsrecon
- jsluice, cariddi, trufflehog, gitleaks

## Performance Considerations

- Use `--project` to organize results and enable typed output exports
- Adjust `threads` and `rate_limit` based on target responsiveness
- For large targets, consider running modules individually and reviewing results before proceeding
- The `full-recon` workflow can take several hours for large scopes; monitor resource usage

## Troubleshooting

### Tool Not Found

If a required tool is not installed, OFX will attempt to install it based on the `tools:` configuration. Ensure you have appropriate permissions and package managers (go, npm, pip, apt, etc.) available.

### Rate Limiting

If tools are failing due to rate limits, reduce `threads` or `rate_limit` inputs.

### Memory Issues

For large scans, monitor memory usage. Consider breaking targets into smaller batches using the `--input` file option.

## License

This collection is provided as part of OFX. See OFX license for terms.

## Contributing

Improvements and additional workflows are welcome. Submit issues and pull requests to the OFX repository.
