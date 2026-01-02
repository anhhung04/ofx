# flow tools

Manage workflow tool dependencies.

## Usage

```bash
ofx flow tools <subcommand> [options]
```

## Subcommands

### install

Install required tools for a workflow.

```bash
ofx flow tools install <workflow>
```

### list

List tools required by a workflow.

```bash
ofx flow tools list <workflow>
```

### check

Check if required tools are installed.

```bash
ofx flow tools check <workflow>
```

## Description

The `tools` command helps manage external tool dependencies required by workflows. Tools are installed in `~/Tools/bin` and automatically added to PATH during workflow execution.

## Examples

### Install workflow tools

```bash
ofx flow tools install recon-workflow.yaml
```

### List required tools

```bash
ofx flow tools list attack-chain
```

### Check tool availability

```bash
ofx flow tools check scan-workflow
```

## Tool Installation

Tools can be installed via:

- **UV** - Python packages via `uv tool install`
- **Binary** - Direct binary downloads
- **Package Manager** - System package managers
- **Custom** - User-defined installation scripts

## Tool Configuration

Define tools in workflow:

```yaml
name: my-workflow
tools:
  - name: nuclei
    install: uv tool install nuclei
  - name: httpx
    install: go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
```

## See Also

- [flow run](run.md)
- [Extending OFX](../../guide/extending-data-modules/index.md)
