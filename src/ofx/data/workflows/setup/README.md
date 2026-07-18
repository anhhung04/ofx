# Setup Workflow Collection

Environment and infrastructure setup workflows for penetration testing and
red team operations.

## Overview

This collection provides workflows for bootstrapping attack infrastructure, setting
up development environments, configuring C2 redirectors, and establishing exfiltration
channels.

### Workflows

#### Infrastructure

- **cloud-setup** — Provision authorized attack infrastructure using AWS EC2 or
  DigitalOcean droplets. Creates instances, configures SSH access, emits connection
  details, and optionally bootstraps a minimal toolchain for subsequent OFX workflows.

- **c2-redirector** — Configure HTTP/HTTPS redirectors for C2 frameworks. Sets up
  domain fronting, CDN routing, and traffic management rules.

#### Tooling

- **pentest-env** — Set up a penetration testing workstation with core packages,
  Go/Python/Ruby tooling, OFX-compatible security tools, wordlists, shell aliases,
  proxychains configuration, and reusable config templates.

#### Data Movement

- **exfil-channels** — Configure data exfiltration channels using DNS, HTTP, ICMP,
  and other covert protocols. Sets up listeners, encodes data paths, and tests
  channel reliability.

#### Security Labs & Tooling

- **docker-lab** — Spin up a disposable Docker Compose security lab with common
  vulnerable targets (DVWA, Juice Shop, Metasploitable, etc.) for authorized
  penetration testing practice.

- **proxy-config** — Configure proxy chains, VPN routing, and SSH tunneling for
  red team operations. Sets up proxychains, torsocks, SSH dynamic forwarding,
  and network namespace isolation.

- **git-secrets-guard** — Set up pre-commit hooks for secret scanning with gitleaks
  and trufflehog. Generates optional CI pipeline integration (GitHub Actions or
  GitLab CI).

## Usage

```bash
# Provision cloud attack infrastructure
ofx flow run cloud-setup -t my-redteam-instance

# Set up a pentest workstation
ofx flow run pentest-env -t /opt/tools

# Configure C2 redirector
ofx flow run c2-redirector -t redirector.example.com

# Set up exfiltration channels
ofx flow run exfil-channels -t c2-server.example.com
```
