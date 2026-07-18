# Code Security Workflow Collection

Source code security analysis workflows for DevSecOps and CI/CD integration.

## Overview

This collection provides workflows for security scanning of source code repositories,
container images, and project dependencies. Each workflow can run standalone or be
integrated into CI/CD pipelines for automated security gates.

### Workflows

#### Secret Detection

- **secrets-hunt** — Deep scan for hardcoded secrets, API keys, tokens, and credentials
  in source code repositories. Uses gitleaks and trufflehog with historical Git commit
  analysis. Includes git-dumper for extracting secrets from bare repositories or
  lost+found directories.

#### Vulnerability Scanning

- **code-scan** — Comprehensive source code security analysis. Scans for vulnerabilities
  (SAST, dependency scanning) and hardcoded secrets in code repositories and directories.

- **dependency-audit** — Dependency vulnerability audit across multiple ecosystems
  (npm, pip, Go, Ruby, etc.) using grype and trivy. Deduplicates findings and reports
  by severity.

#### Container Security

- **container-scan** — Comprehensive container image security analysis. Scans for OS and
  library vulnerabilities, embedded secrets, and Dockerfile best-practice violations
  using multiple engines. Provides deduplicated results.

## Usage

```bash
# Scan a repository for secrets
ofx flow run secrets-hunt -t /path/to/repo

# Audit a container image
ofx flow run container-scan -i nginx:latest

# Run full code security audit
ofx flow run code-scan -t /path/to/repo

# Check project dependencies
ofx flow run dependency-audit -t /path/to/repo
```
