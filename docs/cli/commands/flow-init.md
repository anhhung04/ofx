# flow init

Scaffold a new workflow YAML file pre-configured for IDE autocompletion and validation.

## Usage

```bash
ofx flow init <workflow-name> [options]
```

---

## Arguments

| Argument | Description |
|----------|-------------|
| `workflow-name` | Name of the workflow (used as the filename stem) |

## Options

| Option | Description |
|--------|-------------|
| `-o, --output <path>` | Output directory or full file path (default: current directory) |
| `--force` | Overwrite an existing file |

---

## What It Does

1. **Exports the JSON schema** to `~/.ofx/workflow_schema.json` (regenerated on every run to stay in sync with the installed version).
2. **Writes a starter YAML file** with a `# yaml-language-server: $schema=<path>` comment at the top, pointing to the exported schema.

The schema comment enables full autocompletion and inline validation in editors that support the [YAML Language Server](https://github.com/redhat-developer/yaml-language-server) (VS Code, Neovim, etc.).

---

## Examples

### Create in current directory

```bash
ofx flow init recon-scan
# Creates: ./recon-scan.yml
```

### Create in a specific directory

```bash
ofx flow init my-op -o ~/ops/
# Creates: ~/ops/my-op.yml
```

### Create at an explicit path

```bash
ofx flow init ad-enum -o /projects/red/workflows/ad-enum.yml
```

### Overwrite existing

```bash
ofx flow init recon-scan --force
```

---

## Generated File

The created file includes the schema comment and a minimal valid workflow skeleton:

```yaml
# yaml-language-server: $schema=/home/user/.ofx/workflow_schema.json
name: my-workflow
description: ""

inputs: {}

jobs:
  job1:
    steps:
      - name: step1
        run: echo "hello"
```

---

## IDE Integration

With the schema comment in place:

- **VS Code** (with the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)): hover documentation, field autocompletion, and error squiggles.
- **Neovim** (with `nvim-lspconfig` + `yaml-language-server`): same benefits.
- **JetBrains IDEs**: schema validation is built in; point to the exported JSON file.

---

## See Also

- [flow schema](schema.md) — Export the JSON schema manually or view model trees
- [flow validate](validate.md) — Validate a workflow file against the schema
- [Workflows Guide](../../guide/workflows.md) — Full workflow syntax reference
