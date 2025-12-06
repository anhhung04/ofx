# Shellcode Assembly Sources

This directory contains editable assembly source files for shellcode generation. Users can modify these `.asm` files to customize shellcode behavior.

## Structure

```
shellcodes/
├── linux/
│   ├── Dockerfile         # Docker image for x86 Linux compilation
│   ├── compile.sh         # Compilation script for x86
│   └── src/
│       ├── reverse_tcp.asm  # Reverse shell
│       └── bind_tcp.asm     # Bind shell
├── linux/x64/
│   ├── Dockerfile         # Docker image for x64 Linux compilation
│   ├── compile.sh         # Compilation script for x64
│   └── src/
│       ├── reverse_tcp.asm  # Reverse shell
│       └── bind_tcp.asm     # Bind shell
├── windows/
│   ├── Dockerfile         # Docker image for x86 Windows compilation
│   ├── compile.sh         # Compilation script for x86
│   └── src/
│       ├── reverse_tcp.asm  # Reverse shell
│       └── bind_tcp.asm     # Bind shell
└── windows/x64/
    ├── Dockerfile         # Docker image for x64 Windows compilation
    ├── compile.sh         # Compilation script for x64
    └── src/
        ├── reverse_tcp.asm  # Reverse shell
        └── bind_tcp.asm     # Bind shell
```

## Usage

### Method 1: Msfvenom (Recommended)

If `msfvenom` is installed (from Metasploit Framework), it will be used automatically:

```python
from ofx.api.shellcode import OSShellcodes

sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
payload = sc.create_shellcode(shellcode_type="reverse")
```

### Method 2: Docker-Compiled Assembly (Fallback)

If `msfvenom` is not available, the system automatically falls back to compiling assembly sources using Docker:

```python
from ofx.api.shellcode import OSShellcodes

# Automatic fallback if msfvenom not installed
sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
payload = sc.create_shellcode(shellcode_type="reverse")

# Or force Docker compilation explicitly
payload = sc.create_shellcode(use_docker_compile=True)
```

## Editing Assembly Sources

### 1. Locate the Assembly File

Find the source file you want to modify:
- Linux x86 reverse shell: `linux/src/reverse_tcp.asm`
- Linux x64 bind shell: `linux/x64/src/bind_tcp.asm`
- Windows x86 reverse shell: `windows/src/reverse_tcp.asm`
- Windows x64 bind shell: `windows/x64/src/bind_tcp.asm`

### 2. Edit the Assembly

Open the `.asm` file in your favorite text editor. The assembly uses NASM syntax.

**Important placeholders** (automatically replaced during compilation):
- IP address: `127, 0, 0, 1` or `0x7f, 0x00, 0x00, 0x01`
- Port: `0x11, 0x5c` (default 4444 in network byte order)

Example modification:
```nasm
; Original
push 0x7f          ; 127.0.0.1
push 0x00
push 0x00
push 0x01

; Modified for different syscall
push eax           ; Your custom code
xor ebx, ebx
```

### 3. Rebuild Docker Image (Optional)

If you modified the Dockerfile or compile script:

```bash
cd /path/to/shellcodes/linux/x64
docker build -t ofx-shellcode-linux-x64:latest .
```

### 4. Generate Updated Shellcode

```python
from ofx.api.shellcode import OSShellcodes

sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
# Force recompilation with your modified assembly
payload = sc.create_shellcode(use_docker_compile=True, debug=1)
print(f"Generated {len(payload)} bytes of shellcode")
```

## Compilation Process

1. **IP/Port Substitution**: The compile script reads `LHOST` and `LPORT` environment variables
2. **Assembly Preprocessing**: `sed` replaces placeholder IP/port values in the `.asm` file
3. **NASM Compilation**: Assembly is compiled to object file
4. **Binary Extraction**: `.text` section is extracted as raw shellcode bytes
5. **Output**: Raw shellcode bytes are returned to Python

## Dockerfile Structure

Each Dockerfile follows this pattern:

```dockerfile
FROM ubuntu:22.04

# Install NASM and binutils
RUN apt-get update && \
    apt-get install -y nasm binutils xxd && \
    apt-get clean

WORKDIR /workspace

# Copy compile script
COPY compile.sh /compile.sh
RUN chmod +x /compile.sh

ENTRYPOINT ["/compile.sh"]
```

## Compile Script Pattern

Each `compile.sh` script:
1. Accepts assembly filename as argument
2. Reads `LHOST` and `LPORT` environment variables
3. Converts IP/port to hex format
4. Substitutes placeholders using `sed`
5. Compiles with NASM (format depends on architecture)
6. Extracts raw bytes using `objcopy`
7. Outputs to stdout

## Troubleshooting

### Assembly Compilation Fails

**Error**: "Docker not found in PATH"
```bash
# Install Docker
apt-get install docker.io  # Ubuntu/Debian
brew install --cask docker  # macOS
```

**Error**: "Assembly file not found"
- Check that `.asm` file exists in correct `src/` directory
- Verify filename matches pattern: `{reverse|bind}_tcp.asm`

**Error**: "Compilation produced no output"
- Check compile script for errors
- Verify NASM syntax in `.asm` file
- Run Docker image manually for debugging:
  ```bash
  docker run --rm -v $(pwd)/src:/workspace \
    -e LHOST=192.168.1.100 -e LPORT=4444 \
    ofx-shellcode-linux-x64:latest reverse_tcp.asm | xxd
  ```

### Msfvenom Not Found

**Error**: "msfvenom not found in PATH"

Install Metasploit Framework:
```bash
# Ubuntu/Debian
curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall
chmod 755 msfinstall
./msfinstall

# macOS
brew install metasploit

# Or use Docker
docker pull metasploitframework/metasploit-framework
```

Or use Docker-compiled assembly instead (no msfvenom required):
```python
sc.create_shellcode(use_docker_compile=True)
```

## Advanced Customization

### Adding New Shellcode Types

1. Create new `.asm` file in appropriate `src/` directory
2. Follow existing naming pattern: `<type>_tcp.asm`
3. Use placeholder IP/port values that compile script can replace
4. Test compilation manually before using in code

### Custom Compilation Parameters

Modify `compile.sh` to add custom NASM flags:

```bash
# Example: Enable debugging symbols
nasm -g -f elf64 -o /tmp/shellcode.o /tmp/shellcode.asm
```

### Platform-Specific Notes

**Linux (ELF)**:
- x86: `-f elf32`
- x64: `-f elf64`
- Requires `objcopy` to extract `.text` section

**Windows (PE)**:
- Uses flat binary format: `-f bin`
- Direct output as raw shellcode
- No `objcopy` needed

## Security Considerations

⚠️ **Warning**: This directory contains offensive security tools. Use only in authorized environments.

- Assembly sources are **raw shellcode** without obfuscation
- Generated shellcode may be detected by antivirus/EDR
- For evasion, consider:
  - Encoding (XOR, alphanum)
  - Encryption wrappers
  - Custom packers
  - Polymorphic techniques

## Contributing

When adding new assembly sources:
1. Follow NASM syntax standards
2. Use consistent placeholder patterns for IP/port
3. Test on target architecture
4. Document any special requirements
5. Provide example usage

## Resources

- **NASM Documentation**: https://nasm.us/docs.php
- **x86/x64 Assembly**: https://www.felixcloutier.com/x86/
- **Linux Syscalls**: https://syscalls.kernelgrok.com/
- **Windows API**: https://docs.microsoft.com/en-us/windows/win32/api/
- **Metasploit msfvenom**: https://docs.metasploit.com/docs/using-metasploit/basics/how-to-use-msfvenom.html
