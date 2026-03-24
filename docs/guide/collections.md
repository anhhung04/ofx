# Workflow Collections

Collections are installable packages of reusable workflows. They provide a standardised way to share and manage workflow libraries across teams.

---

## Overview

A **collection** is a Git repository (or local directory) containing one or more workflow files. Once installed, the workflows inside a collection are automatically available to `ofx flow run` — no extra path configuration needed.

Key features:

- **One-command install** — `ofx flow collection add <git-url>`
- **Automatic workflow discovery** — installed collections are added to the workflow search path

---

## Installing Collections

### From a Git URL

```bash
# Full URL
ofx flow collection add https://github.com/myorg/my-workflows.git

# SSH URL
ofx flow collection add git@github.com:myorg/my-workflows.git
```

### From a local directory

```bash
ofx flow collection add ./my-local-collection
```

### Pin a Git ref

```bash
ofx flow collection add https://github.com/myorg/recon-tools.git --ref v1.2.0
```

### Override the local name

```bash
ofx flow collection add https://github.com/myorg/my-workflows.git --name custom-name
```

---

## Using Installed Collections

Once installed, every workflow inside a collection can be referenced by name:

```bash
ofx flow run subdomain-enum --input target=example.com
```

OFX searches the following directories in order:
1. Current working directory
2. `~/.ofx/workflows/`
3. All installed collection directories (`~/.ofx/collections/*/`)

You can also reference collection workflows from a `uses` step inside another workflow:

```yaml
name: full-recon
jobs:
  enum:
    steps:
      - uses: subdomain-enum.yaml
        with:
          target: "{{ inputs.target }}"
```

---

## Managing Collections

### List installed collections

```bash
ofx flow collection list
```

### Show detailed info

```bash
ofx flow collection info recon-tools
```


```bash
# Update a single collection
ofx flow collection update recon-tools

# Update all installed collections
ofx flow collection update
```

### Remove

```bash
ofx flow collection remove recon-tools
```

---
## Creating Your Own Collection

### 1. Create a repository

```
my-collection/
├── subdomain-enum.yaml    # Workflow files
├── port-scan.yaml
└── README.md
```

### 2. Push to GitHub

```bash
git init && git add . && git commit -m "Initial collection"
git remote add origin https://github.com/myorg/my-collection.git
git push -u origin main
```

Others can now install it:

```bash
ofx flow collection add https://github.com/myorg/my-collection.git
```

---

## Storage Layout

```
~/.ofx/collections/
├── installed.json           # Registry of installed collections
├── recon-tools/             # Cloned collection repository
│   ├── subdomain-enum.yaml
│   └── port-scan.yaml
└── base-utils/
    └── helpers.yaml
```

---

## See Also

- [Collection CLI Reference](../cli/commands/collection.md) — Full command reference
- [Workflows](workflows.md) — Workflow syntax and structure
- [Templates](templates.md) — Jinja2 templating in workflows
