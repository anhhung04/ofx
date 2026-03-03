# Workflow Collections

Collections are installable packages of reusable workflows, tools, and resources. They provide a standardised way to share, discover, and manage workflow libraries across teams and the community.

---

## Overview

A **collection** is a Git repository (or local directory) containing one or more workflow files and an optional `collection.yaml` manifest. Once installed, the workflows inside a collection are automatically available to `ofx flow run` — no extra path configuration needed.

Key features:

- **One-command install** — `ofx flow collection add recon-tools`
- **Automatic workflow discovery** — installed collections are added to the workflow search path
- **Dependency resolution** — collections can declare dependencies on other collections
- **Community index** — browse and search shared collections hosted on GitHub
- **Semver version constraints** — pin or constrain dependency versions
- **Migration path** — move from the legacy `ofx asset` system seamlessly

---

## Installing Collections

### From the ofx-workflows organisation (bare name)

```bash
ofx flow collection add recon-tools
```

Bare names resolve to `https://github.com/ofx-workflows/recon-tools`.

### From a GitHub repository

```bash
# org/repo shorthand
ofx flow collection add myorg/my-workflows

# Full URL
ofx flow collection add https://github.com/myorg/my-workflows.git
```

### Pin a Git ref

```bash
ofx flow collection add recon-tools --ref v1.2.0
```

### Override the local name

```bash
ofx flow collection add https://github.com/myorg/my-workflows.git --name custom-name
```

### Skip dependency installation

```bash
ofx flow collection add recon-tools --no-deps
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

### Update to latest

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

## Searching the Community Index

The community index is a curated list of collections hosted at `https://github.com/ofx-workflows/index`.

```bash
# Search by keyword, tag, or description
ofx flow collection search recon

# Force-refresh the cached index
ofx flow collection search recon --refresh
```

Install any result directly:

```bash
ofx flow collection add <name>
```

---

## Creating Your Own Collection

### 1. Create a repository

```
my-collection/
├── collection.yaml        # Optional manifest
├── subdomain-enum.yaml    # Workflow files
├── port-scan.yaml
└── README.md
```

### 2. Add a `collection.yaml` manifest

```yaml
name: my-collection
version: 1.0.0
description: My recon workflow collection
author: security-team
license: MIT
min_ofx_version: "0.4.0"

workflows:
  - subdomain-enum.yaml
  - port-scan.yaml

tools:
  - subfinder
  - nmap

tags:
  - recon
  - scanning

dependencies:
  - name: base-utils
    version: ">=0.2.0"
  - name: myorg/shared-helpers
```

!!! tip "Auto-discovery"
    If you omit the `workflows` list (or leave it empty), OFX will automatically discover all `.yml` and `.yaml` files in the collection directory.

### 3. Manifest fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | **Yes** | Collection name |
| `version` | string | No | Semver version (default: `0.0.0`) |
| `description` | string | No | Human-readable description |
| `author` | string | No | Author or team name |
| `license` | string | No | License identifier (e.g. `MIT`) |
| `min_ofx_version` | string | No | Minimum OFX version required |
| `workflows` | list | No | Workflow files in the collection |
| `tools` | list | No | Tool names the collection needs |
| `dependencies` | list | No | Other collections this depends on |
| `tags` | list | No | Tags for discoverability |

### 4. Push to GitHub

```bash
git init && git add . && git commit -m "Initial collection"
git remote add origin https://github.com/myorg/my-collection.git
git push -u origin main
```

Others can now install it:

```bash
ofx flow collection add myorg/my-collection
```

---

## Dependencies

Collections can declare dependencies on other collections. When you install a collection, its dependencies are resolved and installed automatically (unless `--no-deps` is passed).

```yaml
# collection.yaml
dependencies:
  - name: base-utils
    version: ">=1.0.0"
  - name: myorg/shared-templates
    source: https://github.com/myorg/shared-templates.git
```

### Version constraints

The following operators are supported:

| Operator | Example | Description |
|----------|---------|-------------|
| `>=` | `>=1.0.0` | Greater than or equal |
| `>` | `>1.0.0` | Greater than |
| `<=` | `<=2.0.0` | Less than or equal |
| `<` | `<2.0.0` | Less than |
| `==` | `==1.2.3` | Exact match |
| `!=` | `!=1.0.0` | Not equal |
| `~=` | `~=1.2.0` | Compatible release (>=1.2.0 and <2.0.0) |

### Minimum OFX version

Set `min_ofx_version` to warn users if their OFX installation is too old:

```yaml
min_ofx_version: "0.4.0"
```

If the installed OFX version is below this threshold, a warning is printed during installation.

---

## Migrating from Legacy Assets

If you used the old `ofx asset` system, you can migrate to collections in one step:

```bash
ofx flow collection migrate
```

This reads the legacy `assets.json` registry and re-installs each entry as a collection.

---

## Storage Layout

Collections are stored under `~/.ofx/collections/`:

```
~/.ofx/collections/
├── installed.json           # Registry of installed collections
├── recon-tools/             # Cloned collection repository
│   ├── collection.yaml
│   ├── subdomain-enum.yaml
│   └── port-scan.yaml
└── base-utils/
    ├── collection.yaml
    └── helpers.yaml
```

---

## See Also

- [Collection CLI Reference](../cli/commands/collection.md) — Full command reference
- [Workflows](workflows.md) — Workflow syntax and structure
- [Templates](templates.md) — Jinja2 templating in workflows
