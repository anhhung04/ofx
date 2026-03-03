# flow collection

Manage installable workflow collections — install, update, remove, search, and inspect packages of reusable workflows.

## Usage

```bash
ofx flow collection <subcommand> [options]
```

---

## Subcommands

### add

Install a workflow collection from Git.

```bash
ofx flow collection add <name_or_url> [options]
```

**Arguments:**

- `name_or_url` (required) — Collection name, `org/repo`, or full Git URL.
  Bare names resolve to `https://github.com/ofx-workflows/<name>`.

**Options:**

| Option | Description |
|--------|-------------|
| `-n, --name <name>` | Override the local collection name |
| `-r, --ref <ref>` | Pin a Git tag or branch |
| `--no-deps` | Skip installing collection dependencies |

**Examples:**

```bash
# Install from the ofx-workflows GitHub org
ofx flow collection add recon-tools

# Install from a custom repository
ofx flow collection add myorg/my-workflows

# Pin to a specific tag
ofx flow collection add recon-tools --ref v1.2.0

# Install without dependencies
ofx flow collection add recon-tools --no-deps
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

### search

Search the community collection index.

```bash
ofx flow collection search <query> [options]
```

**Arguments:**

- `query` (required) — Search term matched against name, description, and tags.

**Options:**

| Option | Description |
|--------|-------------|
| `--refresh` | Force-refresh the cached index from remote |

The index is fetched from `https://github.com/ofx-workflows/index` and cached locally for one hour.

**Examples:**

```bash
ofx flow collection search recon
ofx flow collection search scanning --refresh
```

---

### migrate

Migrate legacy asset collections to the new collection system.

```bash
ofx flow collection migrate
```

Reads the legacy `assets.json` registry from `~/.ofx/` and re-installs each entry as a modern collection.

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
