# Scanning Workflows

Host discovery, port scanning, service enumeration, web probing, and SSL/TLS analysis.

## Workflows

### host-discovery
Identify live hosts via ICMP ping sweep on a CIDR range.
```bash
ofx flow run host-discovery --input target=10.0.0.0/24
```
Uses: fping, naabu

### port-scan
Fast SYN scan followed by targeted service detection with nmap.
```bash
ofx flow run port-scan --input target=10.0.0.0/24 --input ports=top-1000
```
Uses: naabu, rustscan, nmap

### web-probe
Probe hosts for HTTP/HTTPS, detect technologies, capture screenshots.
```bash
ofx flow run web-probe --input target=hosts.txt
```
Uses: httpx, whatweb, gowitness

### ssl-audit
TLS certificate analysis, cipher suite audit, CT subdomain discovery.
```bash
ofx flow run ssl-audit --input target=example.com
```
Uses: tlsx, sslscan, testssl.sh
