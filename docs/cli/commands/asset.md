# asset

Manage asset collections and workflow templates.

## Usage

```bash
ofx asset <subcommand> [options]
```

## Subcommands

### create

Create a new asset collection.

```bash
ofx asset create <name> [options]
```

### add

Add workflows to an asset collection.

```bash
ofx asset add <collection> <workflow...>
```

### list

List asset collections.

```bash
ofx asset list
```

### show

Show collection contents.

```bash
ofx asset show <collection>
```

### remove

Remove workflows from collection.

```bash
ofx asset remove <collection> <workflow...>
```

### delete

Delete an asset collection.

```bash
ofx asset delete <collection>
```

## Description

Asset collections group related workflows, templates, and resources for easy reuse and sharing. Think of them as workflow packages or libraries.

## Examples

### Create collection

```bash
ofx asset create recon-tools
```

### Add workflows to collection

```bash
ofx asset add recon-tools \
  subdomain-enum.yaml \
  port-scan.yaml \
  service-detection.yaml
```

### List all collections

```bash
ofx asset list
```

### Show collection contents

```bash
ofx asset show recon-tools
```

### Remove workflow from collection

```bash
ofx asset remove recon-tools old-workflow.yaml
```

### Delete collection

```bash
ofx asset delete outdated-collection
```

## Asset Collection Structure

```
~/.local/share/ofx/workflows/
└── recon-tools/
    ├── subdomain-enum.yaml
    ├── port-scan.yaml
    ├── service-detection.yaml
    └── README.md
```

## Using Collections

Reference workflows from collections:

```yaml
name: full-recon
jobs:
  enum:
    uses: asset://recon-tools/subdomain-enum.yaml
  scan:
    uses: asset://recon-tools/port-scan.yaml
    needs: enum
```

## Collection Metadata

Collections can include metadata:

```yaml
# recon-tools/collection.yaml
name: recon-tools
description: Reconnaissance workflow collection
version: 1.0.0
author: security-team
workflows:
  - subdomain-enum.yaml
  - port-scan.yaml
```

## Sharing Collections

Export collection:

```bash
tar -czf recon-tools.tar.gz ~/.local/share/ofx/workflows/recon-tools/
```

Import collection:

```bash
tar -xzf recon-tools.tar.gz -C ~/.local/share/ofx/workflows/
```

## See Also

- [Workflows](../../guide/workflows/index.md)
- [Templates](../../guide/templates/index.md)
