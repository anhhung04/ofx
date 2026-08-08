# Vulnerability Assessment Workflows

CVE scanning, web application testing, secret discovery, SAST, and container scanning.

## Workflows

### vuln-scan
Nuclei-based vulnerability scanning with severity filtering.
```bash
ofx flow run vuln-scan --input target=urls.txt --input severity=critical,high
```
Uses: nuclei

### web-scan
Web application testing — SQLi, XSS, SSTI, SSRF, directory fuzzing.
```bash
ofx flow run web-scan --input target=https://example.com --input scan_type=all
```
Uses: dirsearch, ffuf, sqlmap, dalfox, tplmap

### secret-scan
Discover leaked credentials, API keys, and tokens in repos and files.
```bash
ofx flow run secret-scan --input target=https://github.com/org/repo
```
Uses: trufflehog, gitleaks

### code-scan
SAST analysis for security vulnerabilities in source code.
```bash
ofx flow run code-scan --input target=./src
```
Uses: semgrep, gitleaks

### container-scan
Vulnerability assessment for Docker images and container registries.
```bash
ofx flow run container-scan --input target=nginx:latest
```
Uses: trivy, grype
