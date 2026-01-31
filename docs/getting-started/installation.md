# Installation

Install OFX using your preferred method.

## Quick Install (pip/uv)

```bash
# Using pip
pip install ofx

# Using uv (recommended)
uv pip install ofx

# Verify
ofx --version
```

## Package Managers

### Debian/Ubuntu (.deb)

```bash
# Download from releases
wget https://github.com/devhah4/ofx/releases/latest/download/ofx_0.3.2-1_all.deb

# Install
sudo dpkg -i ofx_0.3.2-1_all.deb
sudo apt-get install -f  # Fix any missing dependencies

# Verify
ofx --version
```

### Fedora/RHEL/CentOS (.rpm)

```bash
# Download from releases
wget https://github.com/devhah4/ofx/releases/latest/download/ofx-0.3.2-1.noarch.rpm

# Install
sudo rpm -i ofx-0.3.2-1.noarch.rpm

# Verify
ofx --version
```

### Windows (winget)

```powershell
# Install via winget
winget install redteam.OFX

# Verify
ofx --version
```

### From Source

```bash
# Clone repository
git clone https://github.com/devhah4/ofx.git
cd ofx

# Install with uv
uv sync
uv run ofx --version

# Or install globally
pip install -e .
```

## System-Wide Python Import

After installing via package manager, OFX is available as a Python library:

```python
from ofx.api.post import RunnerRegistry, PostSSH
from ofx.api.exploitation.webshell import WebShellClient

# List available runners
print(RunnerRegistry.list_runners())
# ['ssh', 'webshell', 'winrm', 'smbexec', 'wmiexec']
```

## Requirements

- **Python:** 3.12 or higher
- **OS:** Linux, macOS, Windows

## Optional Dependencies

Install optional features:

```bash
# Redis registry support
pip install ofx[redis]

# Memcached registry support
pip install ofx[memcached]

# etcd registry support
pip install ofx[etcd]

# All optional dependencies
pip install ofx[redis,memcached,etcd]
```

## Verify Installation

```bash
# Check version
ofx --version

# Run diagnostics
ofx doctor

# View help
ofx --help
```

---

## Next Steps

- [Quick Start](quickstart.md) — Create your first workflow
- [Core Concepts](concepts.md) — Understand the architecture
