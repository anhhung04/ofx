# dump

Dump and analyze data structures.

## Usage

```bash
ofx dump <type> [options]
```

## Description

The `dump` command extracts and displays internal data structures, configurations, and runtime information. Useful for debugging and inspection.

## Dump Types

### config

Dump current configuration.

```bash
ofx dump config
```

### workflow

Dump workflow structure.

```bash
ofx dump workflow <workflow-file>
```

### secrets

List available secrets (values hidden).

```bash
ofx dump secrets
```

### env

Dump environment variables.

```bash
ofx dump env
```

### tools

List installed tools and paths.

```bash
ofx dump tools
```

## Options

- `--format <format>` - Output format: `json`, `yaml`, `table` (default)
- `--output <file>` - Save to file
- `--full` - Include all details

## Examples

### Dump configuration as JSON

```bash
ofx dump config --format json
```

### Dump workflow to file

```bash
ofx dump workflow scan.yaml --output workflow.json --format json
```

### Full environment dump

```bash
ofx dump env --full
```

## Output Formats

### Table (Default)
Human-readable table format with syntax highlighting.

### JSON
Machine-readable JSON format:

```bash
ofx dump config --format json > config.json
```

### YAML
YAML format for easy editing:

```bash
ofx dump workflow attack.yaml --format yaml
```

## Use Cases

- **Debugging**: Inspect internal state
- **Configuration**: Export current settings
- **Documentation**: Generate workflow documentation
- **Migration**: Export for importing elsewhere

## See Also

- [Workflows](../../guide/workflows/index.md)
