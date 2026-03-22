# flow collection

Manage installable workflow collections — install, update, remove, and inspect packages of reusable workflows.

## Usage

```bash
ofx flow collection <subcommand> [options]
```

---

## Subcommands

### add

Install a workflow collection from a Git URL or local directory.

```bash
ofx flow collection add <source> [options]
```

**Arguments:**

- `source` (required) — Git URL (HTTPS or SSH) or path to a local directory.

**Options:**

| Option | Description |
|--------|-------------|
| `-n, --name <name>` | Override the local collection name |
| `-r, --ref <ref>` | Pin a Git tag or branch |
| `--no-deps` | Skip installing collection dependencies |

**Examples:**

```bash
# Install from a Git URL
ofx flow collection add https://github.com/myorg/my-workflows.git

# Install from a local directory
ofx flow collection add ./my-local-collection

# Pin to a specific tag
ofx flow collection add https://github.com/myorg/recon-tools.git --ref v1.2.0

# Install without dependencies
ofx flow collection add https://github.com/myorg/recon-tools.git --no-deps
```

---

### remove

Remove an installed collection and delete its files.

```bash
ofx flow collection remove <name>
```

**Arguments:**

- `name` (required) — Name of the collection to remove.

Prompts for confirmation before deleting.

---

### update

Pull the latest changes for installed collections.

```bash
ofx flow collection update [name]
```

**Arguments:**

- `name` (optional) — Collection to update. Omit to update all installed collections.

**Examples:**

```bash
# Update a specific collection
ofx flow collection update recon-tools

# Update all
ofx flow collection update
```

---

### list

List all installed collections.

```bash
ofx flow collection list [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--outdated` | Show only collections with newer remote versions |

Displays a table with name, version, source URL, and tags.

---

### info

Show detailed information about an installed collection.

```bash
ofx flow collection info <name>
```

**Arguments:**

- `name` (required) — Collection name.

Displays version, description, author, license, tags, workflows, tools, dependencies, source, pinned ref, and installation date.

---

## Collection Manifest

Collections may include a `collection.yaml` manifest:

```yaml
name: recon-tools
version: 1.0.0
description: Reconnaissance workflow collection
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
    version: ">=1.0.0"
```

If the manifest is absent or the `workflows` list is empty, OFX auto-discovers all `.yml`/`.yaml` files in the collection directory.

---

## See Also

- [Collections Guide](../../guide/collections.md) — How collections work, how to create and share them
- [Workflows](../../guide/workflows.md) — Workflow syntax reference
- [flow run](run.md) — Execute workflows
