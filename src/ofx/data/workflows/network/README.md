# Network & Infrastructure Security Workflow Collection

Network and infrastructure security workflows covering the full reconnaissance and
vulnerability assessment lifecycle: domain/subdomain enumeration, host and port
scanning, web probing, cloud and DevOps audits, OSINT gathering, and comprehensive
pentest pipelines.

## Overview

This collection provides 67 workflows spanning network reconnaissance, infrastructure
assessment, and security auditing. Workflows leverage OFX's task system and typed
outputs for data chaining between phases.

### Workflows

#### Domain & Subdomain Reconnaissance

- **domain-recon** — Full domain recon: WHOIS, DNS, subdomains, HTTP, TLS, WAF, crawling, vulns.
- **domain-scan** — Multi-phase domain scan: subdomain enum → host recon → URL crawl → vuln scan.
- **domain-whois-bulk** — Bulk WHOIS lookup for domain intelligence.
- **domain-permutations** — Domain permutation and typosquatting detection.
- **dns-history** — DNS history enumeration and analysis.
- **crtsh-enum** — Certificate transparency log enumeration.
- **subdomain** — Basic subdomain enumeration.
- **subdomain-recon** — Subdomain recon: passive enum, DNS verification, takeover check.
- **subdomain-scan** — Subdomain scan pipeline: passive + active + verification + probing.
- **subdomain-takeover** — Subdomain takeover vulnerability scanning.
- **recursive-domain-scan** — Recursive domain scanning with permutation generation.
- **takeover-scan** — Takeover vulnerability scanning for subdomains and cloud resources.

#### Host & Network Scanning

- **host-recon** — Host reconnaissance: port discovery, service detection, SSH audit, vulns.
- **host-scan** — Multi-phase host scan: ports → services → SSH → web crawl → vulns.
- **network-discovery** — Network host discovery and service fingerprinting.
- **network-scan** — Internal network scan: host discovery, port sweep, per-host deep scan.
- **network-sweep** — Fast network sweep: host discovery, port scan, default cred check.
- **cidr-recon** — CIDR range host discovery, port scan, service detection.
- **port-scan-pipeline** — Port scanning pipeline combining rapid discovery with detailed enumeration.
- **port-blitz** — Aggressive full-range port scanning.
- **banner-grab** — Service banner grabbing and analysis.
- **service-enum** — Service version detection and enumeration.

#### Web Reconnaissance

- **url-scan** — URL scanning pipeline: crawl → fuzz → vulns.
- **url-discovery** — URL discovery from targets using active and passive sources.
- **web-probe** — HTTP service probing and technology fingerprinting.
- **api-endpoints** — API endpoint discovery and enumeration.
- **vhost-discovery** — Virtual host discovery on a given IP address.
- **backup-files** — Backup file and exposed configuration discovery.

#### Cloud & DevOps Security

- **cloud-enum** — Cloud resource enumeration and security audit.
- **cloud-aws-audit** — AWS-specific cloud security audit.
- **cloud-security-audit** — Multi-cloud security posture assessment.
- **k8s-audit** — Kubernetes cluster security audit.
- **cicd-audit** — CI/CD pipeline security audit.
- **s3-buckets** — S3/GCS/Azure Blob bucket enumeration and exposure check.
- **docker-registry-enum** — Docker registry enumeration and image discovery.
- **firebase-check** — Firebase database exposure and misconfiguration check.

#### OSINT & External Reconnaissance

- **osint** — Comprehensive OSINT gathering from multiple sources.
- **company-recon** — Company reconnaissance: domains, employees, technologies, social media.
- **email-osint** — Email OSINT: harvesting, breach lookup, account enumeration.
- **user-hunt** — User account search across online platforms.
- **asn-recon** — ASN-based reconnaissance: IP ranges, BGP data.
- **shodan-recon** — Shodan-based internet asset discovery.
- **fofa-search** — FOFA search engine queries for internet-facing assets.
- **open-databases** — Open database and data exposure scanning.
- **phone-osint** — Phone number OSINT lookup.
- **smtp-enum** — SMTP server enumeration and user validation.
- **snmp-enum** — SNMP enumeration and information disclosure.

#### Vulnerability Assessment

- **vuln-sweep** — Vulnerability scanning: nuclei, injection testing, secret hunting.
- **vuln-prioritize** — Vulnerability prioritization and triage.
- **ssl-audit** — SSL/TLS security auditing: protocols, ciphers, certificates.
- **ssl-deep** — Deep SSL/TLS analysis: certificate chain, SSH integration.
- **security-headers** — HTTP security header audit and grading.
- **secret-scan** — Secret and credential scanning across URLs, repos, filesystems.
- **supply-chain** — Supply chain security assessment.
- **linux-hardening** — Linux system hardening audit.
- **llm-security-audit** — LLM/ML model security assessment.
- **ad-discovery** — Active Directory service discovery.
- **ldap-enum** — LDAP service enumeration and information gathering.

#### Comprehensive Pipelines

- **full-recon** — Full reconnaissance pipeline (8+ jobs).
- **deep-recon** — Deep reconnaissance with recursive enumeration.
- **quick-recon** — Fast reconnaissance with minimal resource usage.
- **bug-bounty-recon** — Bug bounty-optimized reconnaissance pipeline.
- **pentest-external** — External pentest methodology pipeline.
- **target-profiling** — Target profiling and attack surface mapping.

#### Utilities

- **target-file** — Target file creation utility used by other workflows via `uses:`.
- **gogo-zombie** — Gogo service fingerprinting for large target sets.

## Usage

```bash
# Full domain reconnaissance
ofx flow run domain-recon -t example.com

# Network scan on a CIDR range
ofx flow run network-scan -t 192.168.1.0/24

# Quick port scan
ofx flow run port-scan -t 10.0.0.1 --ports top-1000

# OSINT gathering
ofx flow run osint -t example.com

# Cloud security audit
ofx flow run cloud-security-audit -t my-aws-account

# Bug bounty recon pipeline
ofx flow run bug-bounty-recon -t example.com
```
