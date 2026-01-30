# Run Command

> Execute OFX workflow files with inputs, secrets, and output options

---

## Usage

```bash
ofx flow run <workflow.yml> [OPTIONS]
ofx x run <workflow.yml> [OPTIONS]      # Shorthand alias
```

---

## Options

| Option | Description |
|--------|-------------|
| `--input key=value` | Set input variables (repeatable) |
| `--secret key=value` | Provide secrets (repeatable) |
| `--output <dir>` | Output directory for artifacts |
| `--dry-run` | Validate without executing |
| `--debug` | Show verbose execution logs |

---

## Examples

### Basic Run
```bash
ofx flow run workflows/recon.yml --input target=example.com
```

### With Multiple Inputs
```bash
ofx flow run scan.yml \
  --input target=10.0.0.1 \
  --input ports=22,80,443 \
  --input timeout=300
```

### With Secrets and Output
```bash
ofx flow run exploit.yml \
  --input target=10.0.0.1 \
  --secret API_KEY=xxx \
  --output results/
```

### Dry Run (Validate Only)
```bash
ofx flow run complex_scan.yml --dry-run
```

---

## Tips

- Use `--dry-run` to check for errors before running
- Use `--debug` for troubleshooting and verbose logs
- Outputs and logs are saved in the specified output directory
- Use the `x` alias for faster typing: `ofx x run ...`

---

## See Also

- [**Workflow Syntax**](../../guide/workflows.md) — Complete workflow reference
- [**Inputs & Secrets**](../../guide/secrets-inputs.md) — Managing inputs and secrets
- [**Templates**](../../guide/templates.md) — Jinja2 templating