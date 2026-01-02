# flow validate

Validate workflow syntax and configuration.

## Usage

```bash
ofx flow validate <workflow>
```

## Description

The `validate` command checks workflow files for:

- YAML syntax errors
- Schema validation
- Dependency resolution
- Required field validation
- Type checking

## Arguments

- `workflow` - Path to workflow file or workflow name

## Examples

### Validate a workflow file

```bash
ofx flow validate my-workflow.yaml
```

### Validate a named workflow

```bash
ofx flow validate attack-chain
```

## Validation Checks

| Check | Description |
|-------|-------------|
| **Syntax** | Valid YAML format |
| **Schema** | Matches workflow schema |
| **Dependencies** | All job dependencies exist |
| **Required Fields** | Name, jobs defined |
| **Types** | Correct data types |

## Exit Codes

- `0` - Validation passed
- `1` - Validation failed

## See Also

- [flow run](run.md)
- [flow visualize](visualize.md)
