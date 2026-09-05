# Reconnaissance Workflows

Passive and active information gathering — OSINT, subdomain enumeration, DNS analysis, and cloud asset discovery.

## Workflows

### external-recon
Passive subdomain enumeration, ASN/IP range discovery, and OSINT gathering.
```bash
ofx flow run recon/external-recon --input target=example.com
```
Uses: amass, subfinder, asnmap, mapcidr

### dns-enum
DNS record resolution — A, AAAA, CNAME, MX, NS, TXT, SOA records.
```bash
ofx flow run recon/dns-enum --input target=subdomains.txt
```
Uses: dnsx

### cloud-enum
Cloud resource enumeration — S3 buckets, Azure blobs, GCP storage.
```bash
ofx flow run recon/cloud-enum --input target=example.com --input provider=aws
```
Uses: s3scanner, cloudfox

### osint-gather
Email discovery, employee enumeration, WHOIS lookup, data breach checks.
```bash
ofx flow run recon/osint-gather --input target=example.com
```
Uses: theHarvester, h8mail, whois

### full-recon
Full reconnaissance pipeline — auto-classifies the target (domain, subdomain, CIDR, or IP) and runs the appropriate recon chain end to end, with WAF/CDN detection to flag protected hosts.
```bash
ofx flow run recon/full-recon --input target=example.com
ofx flow run recon/full-recon --input target=10.0.0.0/24
```
Chains: external-recon, subdomain-brute, subdomain-permute, subdomain-takeover, host-discovery, port-scan, web-probe, waf-detect, url-archive, js-analysis.

### subdomain-brute
Active subdomain brute force via DNS wordlist enumeration.
```bash
ofx flow run recon/subdomain-brute --input target=example.com --input wordlist=subs.txt
```
Uses: puredns, dnsx

### subdomain-permute
Permutation enumeration — generate and resolve name variations from known subdomains.
```bash
ofx flow run recon/subdomain-permute --input target=subdomains.txt
```
Uses: alterx, dnsgen, puredns

### subdomain-takeover
Detect dangling CNAMEs and unclaimed services on discovered subdomains.
```bash
ofx flow run recon/subdomain-takeover --input target=subdomains.txt
```
Uses: subzy, nuclei

### url-archive
Aggregate known URLs from web archives (Wayback, Common Crawl, OTX) and passive crawling.
```bash
ofx flow run recon/url-archive --input target=subdomains.txt
```
Uses: waybackurls, gau, katana

### js-analysis
Collect JavaScript files and extract endpoints, secrets, and API keys.
```bash
ofx flow run recon/js-analysis --input target=live_hosts.txt
```
Uses: subjs, katana, SecretFinder

### zone-transfer
Attempt DNS zone transfers (AXFR) against every authoritative nameserver.
```bash
ofx flow run recon/zone-transfer --input target=example.com
```
Uses: dig
