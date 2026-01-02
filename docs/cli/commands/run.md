# Run Command

Executes an OFX workflow YAML file, running all jobs and steps as defined. Supports input variables, secrets, and output options.


## Usage
```bash
ofx flow run <workflow.yml> [OPTIONS]
```
---
- `--dry-run`: Validate workflow without executing

---

## Example: Run a Workflow
```bash
ofx flow run workflows/recon.yml --input target=example.com
```

## Example: With Secrets and Output
```bash
```
## Tips
- Use `--debug` for troubleshooting and verbose logs
---
## Usage
```bash
ofx flow run <workflow.yml> [OPTIONS]
```

---
## Options
- `--input key=value`: Set input variables (can be repeated)
- `--secret key=value`: Provide secrets (can be repeated)
- `--output <dir>`: Specify output directory for artifacts
- `--dry-run`: Validate workflow without executing
- `--debug`: Show detailed execution logs

---
## Example: Run a Workflow
```bash
ofx flow run workflows/recon.yml --input target=example.com
```

## Example: With Secrets and Output
```bash
ofx flow run workflows/exploit.yml --input target=10.0.0.1 --secret API_KEY=xxx --output results/
```

---
## Tips
- Use `--dry-run` to check for errors before running
- Use `--debug` for troubleshooting and verbose logs
- Outputs and logs are saved in the specified output directory

---
## See Also
- [Workflow Syntax](../../guide/workflows/index.md)
- [Inputs & Secrets](../../guide/secrets-inputs/index.md)

## See Also
- [Workflow Syntax](../../guide/workflows/index.md)
- [Inputs & Secrets](../../guide/secrets-inputs/index.md)