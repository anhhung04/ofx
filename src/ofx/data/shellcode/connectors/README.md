# Custom Shellcode Connectors

Drop custom connector files here - they're auto-discovered and registered.

## Quick Start

**1. Copy template:**
```bash
cp example_connector.py my_connector.py
```

**2. Implement connector:**
```python
from ofx.data.shellcode.connectors.base import ShellcodeConnector
import subprocess

class MyToolConnector(ShellcodeConnector):
    def __init__(self):
        super().__init__(name="mytool", description="My tool wrapper")
    
    def generate(self, os_target, arch, shell_type, ip, port, **kwargs):
        cmd = ['mytool', '--os', os_target, '--arch', arch, 
               '--ip', ip, '--port', str(port)]
        result = subprocess.run(cmd, capture_output=True, check=True)
        return result.stdout
    
    def _check_availability(self):
        return shutil.which('mytool') is not None
```

**3. Use it:**
```python
from ofx.api.shellcode import OSShellcodes

sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
payload = sc.create_shellcode(connector_name="mytool")
```

## Connector Patterns

## Connector Patterns

### 1. CLI Tool Wrapper
```python
class MyToolConnector(ShellcodeConnector):
    def generate(self, os_target, arch, shell_type, ip, port, **kwargs):
        cmd = ['mytool', '--os', os_target, '--arch', arch, 
               '--ip', ip, '--port', str(port)]
        result = subprocess.run(cmd, capture_output=True, check=True)
        return result.stdout
```

### 2. Remote SSH Execution
```python
from ofx.data.shellcode.connectors.remote import RemoteSSHConnector
from ofx.api.shellcode.connectors import get_registry

ssh = RemoteSSHConnector(
    host='kali.local',
    user='pentester',
    identity_file='~/.ssh/id_rsa'
)
get_registry().register_connector_instance(ssh)
```

### 3. HTTP API Client
```python
from ofx.data.shellcode.connectors.remote import RemoteHTTPConnector

http = RemoteHTTPConnector(
    base_url='https://shellcode-api.example.com',
    api_key='your-api-key'
)
get_registry().register_connector_instance(http)
```

### 4. Programmatic Generator
```python
import struct

class CustomShellcodeConnector(ShellcodeConnector):
    def generate(self, os_target, arch, shell_type, ip, port, **kwargs):
        ip_bytes = bytes(map(int, ip.split('.')))
        port_bytes = struct.pack('>H', port)
        return b'\x90' * 10 + ip_bytes + port_bytes + b'\xcc'
```

## API Reference

**Required Methods:**
- `__init__()` - Set name and description
- `generate(os_target, arch, shell_type, ip, port, **kwargs)` - Generate shellcode
- `_check_availability()` - Return True if dependencies met

**Optional Methods:**
- `get_supported_platforms()` - Return list of (os, arch, type) tuples

**Custom Parameters:**
```python
def generate(self, os_target, arch, shell_type, ip, port, 
             custom_params=None, **kwargs):
    custom_params = custom_params or {}
    obfuscation = custom_params.get('obfuscation', 'low')
    # Use custom parameters...
```

## Testing

```python
from ofx.api.shellcode.connectors import get_connector

connector = get_connector('my-connector')
if connector and connector.is_available():
    shellcode = connector.generate(
        os_target='linux', arch='x64', shell_type='reverse',
        ip='127.0.0.1', port=4444
    )
    print(f"✓ Generated {len(shellcode)} bytes")
else:
    print("✗ Connector not available")
```

## Best Practices

1. **Validate inputs** - Check os_target, arch, ip, port
2. **Handle errors** - Raise `RuntimeError` with clear messages
3. **Check availability** - Implement `_check_availability()` properly
4. **Log appropriately** - Use Python logging module
5. **Document usage** - Add docstrings and examples

## Troubleshooting

## Troubleshooting

**Connector not found:**
- File must not start with `_` or be named `__init__.py`
- Class must inherit from `ShellcodeConnector`
- Check logs for loading errors

**Import errors:**
```python
from ofx.data.shellcode.connectors.base import ShellcodeConnector
```

**Availability issues:**
- Implement `_check_availability()` to return `True`/`False`
- Check logs for dependency issues

---

⚠️ **Security:** Validate inputs, review third-party connectors, never commit credentials.
