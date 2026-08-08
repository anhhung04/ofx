# docs

Display OFX API documentation and data directory information.

## Usage

```bash
ofx docs [options]
```

## Description

Displays interactive API documentation for all OFX modules, functions, and classes directly in the terminal. When run without arguments, shows data directory locations where you can extend OFX with custom workflows and templates.

The documentation is auto-generated from docstrings and type hints with beautiful formatting using Rich.

## Data Directories

### User Data Directory
**Location:** `~/.ofx/`

This is where you can add custom content to extend OFX:

- `workflows/` - Place custom workflow YAML files here. They will be automatically discovered when running workflows.
- `secrets/` - Store unencrypted secrets as plain text files (one secret per file).
- `secrets.enc` - Encrypted secrets store managed by `ofx secret` commands.

### Built-in Data Directory
**Location:** `{package}/ofx/data/` (inside the installation)

Contains OFX's built-in templates and modules:

- `shellcode/` - Shellcode templates for various architectures and payloads
- `webshell/` - Webshell templates (PHP, ASP, ASPX, JSP, etc.)
- `exploit/` - Exploit modules and payloads

## Options

- `--module`, `-m <module>` - Specific API module name to document
- `--function`, `-f <function>` - Specific function to display details for (supports Class.method syntax)
- `--list`, `-l` - List all available API modules

## Examples

### View data directories

```bash
ofx docs
```

Shows a formatted panel with both user and built-in data directory locations, helping you understand where to place custom files.

### List all available modules

```bash
ofx docs --list
```

Shows a table of all available API modules with descriptions.

### View module documentation

```bash
ofx docs --module webshell
```

Displays complete documentation for the webshell module including all functions and classes.

### View specific function documentation

```bash
ofx docs --module exploit --function http_request
```

Shows detailed documentation for a specific function.

### View class method documentation

```bash
ofx docs --module webshell --function WebShell.execute
```

Shows documentation for a specific class method.

## Extending OFX

### Adding Custom Workflows

1. Create a YAML workflow file (e.g., `my-custom-workflow.yml`)
2. Place it in `~/.ofx/workflows/`
3. Run it with `ofx flow run my-custom-workflow`

Example custom workflow structure:

```yaml
name: My Custom Workflow
description: Custom workflow for specific tasks

jobs:
  setup:
    name: Setup Environment
    steps:
      - name: Install tools
        run: echo "Installing custom tools..."
```

### Adding Custom Secrets

#### Option 1: Plain text files (for development)
```bash
# Create a secret file
echo "my-api-key-123" > ~/.ofx/secrets/my_api_key

# Use in workflow
ofx flow run workflow --input api_key='{{ secrets.my_api_key }}'
```

#### Option 2: Encrypted store (recommended for production)
```bash
# Add secret to encrypted store
ofx secret add my_api_key

# List all secrets
ofx secret list

# Use in workflows automatically via secrets context
```

### Using Built-in Templates

Built-in templates can be referenced in your workflows:

```yaml
jobs:
  exploit:
    steps:
      - name: Generate webshell
        uses: webshell-generator
        run_with:
          type: php
          password: custom_pass
```

## Documentation Display Features

The terminal documentation provides:

### API Reference
- Function signatures with type hints
- Parameter descriptions with types and defaults
- Return types
- Usage examples from docstrings
- Pydantic model schemas for complex types

### Rich Formatting
- Color-coded syntax highlighting
- Formatted tables for parameters and fields
- Code syntax highlighting for examples
- Tree structure for nested information
- Interactive panels with borders

## Available API Modules

Documentation is available for:

1. **Reconnaissance**: 
   - `fofa` - FOFA search engine integration
   - `shodan` - Shodan API client
   - `zoomeye` - ZoomEye search integration
   - `oob` - Out-of-band interaction utilities

2. **Exploitation**: 
   - `http` - HTTP client utilities
   - `exploit` - General exploit utilities
   - `shellcode` - Shellcode generation
   - `webshell` - Webshell generation and management

3. **Post-Exploitation**: 
   - `file` - File operations and transfers
   - `httpserver` - HTTP server utilities
   - `network` - Network utilities and scanning
   - `workflow` - Workflow execution APIs
   - `strings` - String manipulation and encoding
   - `utils` - General utility functions

## Tips

- **Workflow Discovery**: Workflows in `~/.ofx/workflows/` are automatically discovered
- **Current Directory**: Workflows in the current directory take precedence over user data directory
- **Secret Priority**: Encrypted secrets (`secrets.enc`) take priority over plain text files
- **Data Isolation**: User data is isolated from built-in data, making updates safe
- **Environment Variables**: Set `OFX_SECRETS_DIR` to use a custom secrets location

## See Also

- [API Overview](../../api/overview.md)
- [Webshell API](../../api/overview.md)
- [HTTP API](../../api/overview.md)
- [Workflows Guide](../../guide/workflows.md)
- [Secrets and Inputs](../../guide/secrets-inputs.md)
