# api

Display OFX library (`ofx.lib`) reference documentation in the terminal.

## Usage

```bash
ofx api show [options]
```

## Description

Displays interactive reference documentation for all `ofx.lib` modules, functions, and classes directly in the terminal. The documentation is auto-generated from docstrings and type hints with Rich formatting.

## Options

- `--module`, `-m <module>` — Specific library module name to document
- `--function`, `-f <function>` — Specific function to display details for (supports `Class.method` syntax)
- `--list`, `-l` — List all available library modules

## Examples

### List all available modules

```bash
ofx api show --list
```

Shows a table of all available `ofx.lib` modules with descriptions.

### View module documentation

```bash
ofx api show --module webshell
```

Displays complete documentation for the webshell module including all functions and classes.

### View specific function documentation

```bash
ofx api show --module http --function fetch
```

Shows detailed documentation for a specific function.

### View class method documentation

```bash
ofx api show --module webshell --function WebShell.execute
```

Shows documentation for a specific class method.

## Documentation Display Features

### API Reference
- Function signatures with type hints
- Parameter descriptions with types and defaults
- Return types
- Usage examples from docstrings

### Rich Formatting
- Color-coded syntax highlighting
- Formatted tables for parameters and fields
- Code syntax highlighting for examples
- Tree structure for nested information

## See Also

- [Library Overview](../../lib/overview.md)
- [flow modules](modules.md) — List workflow-callable modules (builtins, library wrappers, tools)
- [Workflows Guide](../../guide/workflows.md)
