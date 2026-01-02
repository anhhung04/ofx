# flow update

Update workflow definitions from templates and modules.

## Usage

```bash
ofx flow update [workflow] [options]
```

## Description

Updates workflow files with latest templates, resolves template references, and refreshes workflow definitions from remote sources.

## Options

- `--all` - Update all workflows
- `--check` - Check for updates without applying
- `--source <url>` - Update from specific source

## Examples

### Update specific workflow

```bash
ofx flow update my-workflow.yaml
```

### Update all workflows

```bash
ofx flow update --all
```

### Check for updates

```bash
ofx flow update --check --all
```

### Update from source

```bash
ofx flow update --source https://github.com/user/workflows
```

## Update Process

1. Check template references
2. Resolve remote includes
3. Download updated templates
4. Merge with local customizations
5. Validate updated workflow

## Template Resolution

Workflows can reference templates:

```yaml
name: my-workflow
template: base-recon
jobs:
  scan:
    uses: github.com/user/workflows/scan.yaml
```

The `update` command resolves these references and fetches latest versions.

## See Also

- [flow run](run.md)
- [Templates Guide](../../guide/templates/index.md)
