# Workflow Collections

Collections are installable packages of reusable workflows, tools, and resources. They provide a standardised way to share and manage workflow libraries across teams.

---

## Overview

A **collection** is a Git repository (or local directory) containing one or more workflow files and an optional `collection.yaml` manifest. Once installed, the workflows inside a collection are automatically available to `ofx flow run` — no extra path configuration needed.

Key features:

- **One-command install** — `ofx flow collection add <git-url>`
- **Automatic workflow discovery** — installed collections are added to the workflow search path
- **Dependency resolution** — collections can declare dependencies on other collections
- **Semver version constraints** — pin or constrain dependency versions

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

### Skip dependency installation

```bash
ofx flow collection add https://github.com/myorg/recon-tools.git --no-deps
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
ofx flow collection add https://github.com/myorg/my-collection.git
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
| `>=` | `>=1.0.0` | Greater than or equal |
| `>` | `>1.0.0` | Greater than |
| `<=` | `<=2.0.0` | Less than or equal |
| `<` | `<2.0.0` | Less than |
| `==` | `==1.2.3` | Exact match |
| `!=` | `!=1.0.0` | Not equal |
| `~=` | `~=1.2.0` | Compatible release (>=1.2.0 and <2.0.0) |

### Minimum OFX version


```yaml
min_ofx_version: "0.4.0"
```

If the installed OFX version is below this threshold, a warning is printed during installation.

---


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
