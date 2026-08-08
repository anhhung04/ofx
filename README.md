# Offensive Flow Executor (OFX)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
![Build](https://img.shields.io/badge/build-passing-brightgreen)

Red team workflow engine — define attack chains as YAML, run jobs in parallel, execute on cloud infrastructure, and keep outputs organized per engagement.

**Docs:** [anhhung04.github.io/ofx-docs/](https://anhhung04.github.io/ofx-docs/)

---

## Quick Start

```bash
uv tool install ofx
ofx flow run external-recon --input target=example.com
```

```yaml
# my-recon.yml
name: recon
jobs:
  scan:
    steps:
      - name: port-scan
        run: nmap -sV -sC {{ inputs.target }} -oA {{ env.OFX_RUN_DIR }}/nmap
      - name: web-probe
        run: httpx -l {{ env.OFX_RUN_DIR }}/nmap.xml -tech-detect -silent
```

## Features

- **YAML Workflows** — Define jobs with parallel execution and dependency chains
- **Cross-platform** — Linux, macOS, Windows; arm64 and amd64
- **Two step types** — `run:` for shell commands, `script:` for Python
- **Jinja2 templating** — Access `inputs`, `secrets`, `env`, `matrix`, `ctx`
- **Cloud execution** — AWS EC2 and DigitalOcean provisioning
- **34 built-in workflows** — Recon, scan, vuln, exploit, post-exploit, utility
- **Detached sessions** — Long-running background jobs with status polling
- **Secrets management** — Encrypted KeePass-based credential store

## Workflow Collections

| Collection | Count | Purpose |
|---|---|---|
| **recon/** | 4 | OSINT, subdomain, DNS, cloud discovery |
| **scan/** | 4 | Host discovery, port scan, web probe, SSL |
| **vuln/** | 5 | Nuclei, web app, secrets, SAST, containers |
| **exploit/** | 6 | AD, credentials, hash crack, C2, payloads |
| **post/** | 8 | Priv esc, lateral, dump, persistence, exfil, OPSEC |
| **utility/** | 3 | Parse targets, extract IOCs, export results |
| **setup/** | 4 | Cloud infra, Docker lab, Git guard, proxy |

## Development

```bash
git clone https://github.com/anhhung04/ofx
cd ofx
uv sync
uv run --extra test pytest
```

## License

MIT — see [LICENSE](LICENSE)