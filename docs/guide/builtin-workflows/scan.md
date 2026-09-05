# Scanning Workflows

Host discovery, port scanning, service enumeration, web probing, and SSL/TLS analysis.

## Workflows

### host-discovery
Identify live hosts via ICMP ping sweep on a CIDR range.
```bash
ofx flow run scan/host-discovery --input target=10.0.0.0/24
```
Uses: fping, naabu

### port-scan
Fast SYN scan followed by targeted service detection with nmap.
```bash
ofx flow run scan/port-scan --input target=10.0.0.0/24 --input ports=top-1000
```
Uses: naabu, rustscan, nmap

### web-probe
Probe hosts for HTTP/HTTPS, detect technologies, capture screenshots.
```bash
ofx flow run scan/web-probe --input target=hosts.txt
```
Uses: httpx, whatweb, gowitness

### ssl-audit
TLS certificate analysis, cipher suite audit, CT subdomain discovery.
```bash
ofx flow run scan/ssl-audit --input target=example.com
```
Uses: tlsx, sslscan, testssl.sh

### waf-detect
Fingerprint WAF/CDN providers in front of targets and produce a filtered target list so protected hosts are skipped by aggressive scans.
```bash
ofx flow run scan/waf-detect --input target=hosts.txt
```
Uses: cdncheck, wafw00f

### dir-fuzz
Directory/file brute force with built-in WAF/CDN detection — protected targets are skipped unless `--input force=true`.
```bash
ofx flow run scan/dir-fuzz --input target=live_urls.txt --input wordlist=common.txt
```
Uses: waf-detect, ffuf

### vhost-fuzz
Discover hidden virtual hosts by fuzzing Host headers against an IP.
```bash
ofx flow run scan/vhost-fuzz --input target=10.0.0.5 --input base_domain=example.com
```
Uses: cdncheck, ffuf
