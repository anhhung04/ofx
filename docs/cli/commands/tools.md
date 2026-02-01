# flow tools

Install and manage workflow tool dependencies.

## Usage

```bash
ofx flow tools [workflow_name] [options]
```

## Arguments

- `workflow_name` - Name of the workflow to install tools for (optional if using --all)

## Options

- `--all` - Install tools from all workflows in the configured directories

## Description

The `tools` command installs external tool dependencies required by workflows. Tools are installed in `~/Tools/bin` and automatically added to PATH during workflow execution.

The command scans workflows for `tools` configuration and installs any missing dependencies using the specified installation methods.

## Examples

### Install tools for a specific workflow

```bash
ofx flow tools recon-workflow
```

### Install tools for a workflow file

```bash
ofx flow tools ./workflows/attack-chain.yml
```

### Install tools from all workflows

```bash
ofx flow tools --all
```

This will scan all workflow files (`.yml`, `.yaml`) in:
- Current directory
- `~/.local/share/ofx/workflows/` (and other configured directories)

## Tool Installation

Tools are installed using the commands specified in workflow configuration. The installer supports:

- **UV packages** - `uv tool install <package>`
- **Go binaries** - `go install <package>@latest`
- **Cargo packages** - `cargo install <package>`
- **NPM packages** - `npm install -g <package>`
- **Static binaries** - `curl` downloads
- **Custom commands** - Any shell command

### Installation Process

1. **Discovery** - Scans workflow YAML for tools configuration
2. **Check** - Verifies if tools are already installed
3. **Install** - Executes installation commands for missing tools
4. **Report** - Displays summary of installed, skipped, and failed tools

## Tool Configuration

Define tools in your workflow:

```yaml
name: my-workflow
tools:
  nuclei: uv tool install projectdiscovery-nuclei
  httpx: go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
  jq: |
    curl -fSsL https://github.com/jqlang/jq/releases/download/jq-1.7/jq-linux64 \
      -o ~/Tools/bin/jq && chmod +x ~/Tools/bin/jq
```

### Advanced Tool Configuration

For more control, use the extended configuration format:

```yaml
tools:
  nuclei:
    install: uv tool install projectdiscovery-nuclei
    check: nuclei -version
    post_install: nuclei -update-templates
  
  custom-tool:
    install: |
      cd /tmp && 
      git clone https://github.com/user/tool.git && 
      cd tool && make install
    check: which custom-tool
```

**Configuration Options:**
- `install` - Command to install the tool (required)
- `check` - Command to verify if tool is already installed (optional)
- `post_install` - Command to run after successful installation (optional)

## Output

The command displays:

1. **Tools Table** - Shows all tools with install commands and current status
2. **Installation Progress** - Real-time feedback during installation
3. **Summary** - Final count of installed, skipped, and failed tools

Example output:

```
┌──────────────────────────────────────────────────────────┐
│                    Tools to Install                      │
├──────────┬──────────────────────────────────┬───────────┤
│ Tool     │ Install Command                  │ Status    │
├──────────┼──────────────────────────────────┼───────────┤
│ nuclei   │ uv tool install projectdisco...  │ ✗ Not... │
│ httpx    │ go install -v github.com/pro...  │ ✓ Inst...│
│ jq       │ curl -fSsL https://github.co...  │ ✗ Not... │
└──────────┴──────────────────────────────────┴───────────┘

Installing tools...

✓ Successfully installed nuclei
✗ Failed to install jq: Command failed

Installation Summary:
  Installed: 1
  Skipped: 1
  Failed: 1
```

## Tool Directory

All tools are installed to:
- **Linux/macOS**: `~/Tools/bin/`
- **Environment**: `UV_TOOL_BIN_DIR` is set to this directory

This directory is automatically prepended to PATH during workflow execution.

## Template Support

Tool installation commands support Jinja2 templates for dynamic configuration:

```yaml
tools:
  custom-tool: |
    {{ sudo }} apt-get install -y my-tool
    {{ tools_bin_dir }}/my-tool --version
```

**Available template variables:**
- `{{ sudo }}` - `sudo` if not root, empty otherwise
- `{{ tools_dir }}` - Path to `~/Tools/`
- `{{ tools_bin_dir }}` - Path to `~/Tools/bin/`
- `{{ python }}` - Python executable path
- `{{ pip_install('pkg') }}` - Generate pip install command

See [Templates Guide](../../guide/templates.md) for more template functions.

## Error Handling

The installer continues on errors and reports failed installations in the summary. To troubleshoot:

1. Check the error message in the output
2. Verify the installation command is correct
3. Ensure prerequisites are installed
4. Run the install command manually for debugging

## See Also

- [flow run](run.md) - Run workflows with installed tools
- [Templates Guide](../../guide/templates.md) - Template system reference
- [Workflows Guide](../../guide/workflows.md) - Workflow configuration

