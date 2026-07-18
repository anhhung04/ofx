# Web Application Security Workflow Collection

Comprehensive web application security testing workflows — vulnerability scanning,
API security, HTTP analysis, and full web audits.

## Overview

This collection provides 26 workflows covering the full spectrum of web application
security testing, from reconnaissance and fingerprinting to deep vulnerability scanning
and exploitation verification.

### Workflows

#### API Security

- **api-fuzz** — REST API endpoint fuzzing for IDOR, method tampering, parameter
  pollution, and auth bypass vulnerabilities.
- **api-security-audit** — Comprehensive API security audit with GraphQL fingerprinting,
  endpoint discovery, OpenAPI schema testing, and cherrybomb checks.
- **graphql-audit** — GraphQL API security audit: introspection query, schema extraction,
  and query complexity analysis.

#### Vulnerability Scanning

- **sqli-scan** — SQL injection scanning with multiple techniques and evasion methods.
- **ssrf-scan** — Server-Side Request Forgery scanner via URL parameter testing.
- **ssti-scan** — Server-Side Template Injection testing with parameter discovery.
- **command-injection** — OS command injection testing using multiple payload techniques.
- **xxe-scan** — XML External Entity injection testing.
- **nosql-injection** — NoSQL injection testing for MongoDB, CouchDB, Redis, and others.
- **nikto-scan** — Web server vulnerability scanning for dangerous files and misconfigs.

#### HTTP & Infrastructure

- **cors-scan** — CORS misconfiguration scanner: reflected origins, null origin, SSL bypass.
- **header-audit** — HTTP security header audit — CSP, HSTS, X-Frame-Options, and more.
- **request-smuggling** — HTTP request smuggling detection for CL.TE and TE.CL attacks.
- **cache-poison** — Web cache poisoning detection via header injection.

#### Authentication & Tokens

- **jwt-audit** — JWT security audit: algorithm confusion, weak secrets, key injection.
- **oob-inject** — Out-of-band injection tester with Interactsh callbacks.

#### Content Discovery

- **url-crawl** — Active crawling and passive URL sources with live probing.
- **url-fuzz** — Directory brute-forcing with intelligent calibration.
- **url-dirsearch** — Directory/file discovery using dirsearch.
- **url-params-fuzz** — Parameter fuzzing for hidden parameters and injection points.
- **url-secrets-hunt** — Secret hunting in web responses and JavaScript.
- **url-vuln** — URL vulnerability scanning with nuclei and specialized tools.

#### Platform-Specific

- **wordpress** — WordPress-specific security audit: version detection, plugin enumeration,
  vulnerability scanning, and configuration checks.

#### Full Audits

- **web-full-audit** — Comprehensive web application audit combining port discovery,
  fingerprinting, directory brute-forcing, parameter fuzzing, and vulnerability scanning.
- **web-fingerprint** — Web technology fingerprinting: WAF detection, platform identification,
  and technology stack mapping.
- **js-analysis** — JavaScript endpoint and secret extraction via crawling and analysis.

## Usage

```bash
# Full web application audit
ofx flow run web-full-audit -t https://target.com

# Scan for SQL injection
ofx flow run sqli-scan -t https://target.com/page?id=1

# API security audit
ofx flow run api-security-audit -t https://api.target.com

# WordPress security check
ofx flow run wordpress -t https://target.com
```
