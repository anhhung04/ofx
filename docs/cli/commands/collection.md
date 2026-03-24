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

**Examples:**

```bash
# Install from a Git URL
ofx flow collection add https://github.com/myorg/my-workflows.git

# Install from a local directory
ofx flow collection add ./my-local-collection

# Pin to a specific tag
ofx flow collection add https://github.com/myorg/recon-tools.git --ref v1.2.0
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

Displays source, pinned ref, path, installation date, and discovered workflows.

---

## See Also

- [Collections Guide](../../guide/collections.md) — How collections work, how to create and share them
- [Workflows](../../guide/workflows.md) — Workflow syntax reference
- [flow run](run.md) — Execute workflows
