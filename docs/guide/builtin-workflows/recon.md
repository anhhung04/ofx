# Reconnaissance Workflows

Passive and active information gathering — OSINT, subdomain enumeration, DNS analysis, and cloud asset discovery.

## Workflows

### external-recon
Passive subdomain enumeration, ASN/IP range discovery, and OSINT gathering.
```bash
ofx flow run external-recon --input target=example.com
```
Uses: amass, subfinder, asnmap, mapcidr

### dns-enum
DNS record resolution — A, AAAA, CNAME, MX, NS, TXT, SOA records.
```bash
ofx flow run dns-enum --input target=subdomains.txt
```
Uses: dnsx

### cloud-enum
Cloud resource enumeration — S3 buckets, Azure blobs, GCP storage.
```bash
ofx flow run cloud-enum --input target=example.com --input provider=aws
```
Uses: s3scanner, cloudfox

### osint-gather
Email discovery, employee enumeration, WHOIS lookup, data breach checks.
```bash
ofx flow run osint-gather --input target=example.com
```
Uses: theHarvester, h8mail, whois
