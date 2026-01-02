# doctor

Diagnose and check system dependencies.

## Usage

```bash
ofx doctor [subcommand] [options]
```

## Subcommands

### check

Run comprehensive system health check.

```bash
ofx doctor check [--verbose]
```

### install-help

Show installation instructions for tools.

```bash
ofx doctor install-help [tool]
```

## Description

The `doctor` command diagnoses your system environment and checks for:

- Essential tools (git, python3)
- Recommended tools (uv, docker, go, node)
- Network connectivity
- System resources (disk, memory)
- OFX directories and permissions

## Options

- `--verbose, -v` - Show detailed information including optional tools

## Examples

### Basic health check

```bash
ofx doctor check
```

### Detailed check with recommendations

```bash
ofx doctor check --verbose
```

### Get installation help

```bash
ofx doctor install-help docker
```

### Get all installation commands

```bash
ofx doctor install-help
```

## Health Checks

### Essential Tools

| Tool | Purpose | Install Command |
|------|---------|-----------------|
| `git` | Version control | `sudo apt install git` |
| `python3` | Runtime environment (≥3.10) | `sudo apt install python3` |

### Recommended Tools

| Tool | Purpose | Install Command |
|------|---------|-----------------|
| `uv` | Fast Python package installer | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `docker` | Container runtime | `curl https://get.docker.com \| sh` |
| `go` | Go language tools | `sudo apt install golang-go` |
| `node` | Node.js runtime | `sudo apt install nodejs npm` |

### System Health

- **Network**: Connectivity to GitHub, Google DNS
- **DNS**: Domain resolution check
- **Disk**: Free space (>2GB required)
- **Memory**: Memory usage (<90% recommended)
- **OFX Directories**: Existence and permissions

## Output

The doctor command provides color-coded output:

- ✅ Green: Check passed
- ❌ Red: Critical failure
- ⚠️ Yellow: Warning/recommendation

## Exit Codes

- `0` - All critical checks passed
- `1` - One or more critical checks failed

## Installing Missing Tools

The doctor will detect your Linux distribution and provide appropriate installation commands:

- **Debian/Ubuntu**: `apt` commands
- **RedHat/Fedora**: `dnf` commands  
- **Arch**: `pacman` commands
- **OpenSUSE**: `zypper` commands

## See Also

- [Getting Started](../../getting-started/quickstart/index.md)
