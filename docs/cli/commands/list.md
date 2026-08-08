# List Workflows

List available workflows across local/user directories, built-in OFX workflows, and installed collection workflows.

---

## Usage

```bash
ofx flow list [options]
```

---

## What it lists

`ofx flow list` aggregates workflows from:

- Current working directory
- `~/.ofx/workflows`
- Built-in packaged workflows
- Installed collections (`ofx flow collection add ...`)

---

## Options

| Option | Short | Description |
|---|---|---|
| `--builtin` | `-b` | Show only built-in workflows |
| `--collection <name>` | `-c` | Show workflows from a specific installed collection |
| `--tag <tag>` | `-t` | Filter by tag (repeatable, OR logic) |
| `--search <text>` | `-s` | Search by name, description, or tags |
| `--tags` | | Show tags alongside each workflow name |
| `--list-tags` | | List all available tags with workflow counts |

---

## Examples

```bash
# List everything available
ofx flow list

# Show only built-in workflows
ofx flow list --builtin

# Filter by tag (multiple tags use OR logic)
ofx flow list --tag recon --tag dns

# Search across name, description, and tags
ofx flow list --search "subdomain"

# Show tags alongside names
ofx flow list --tags

# List all available tags with counts
ofx flow list --list-tags

# Combine filters
ofx flow list --builtin --tag recon --tags
```

---

## See Also

- [Info Command](info.md)
- [Run Command](run.md)
- [Collection Command](collection.md)
- [Built-in Workflows Guide](../../guide/builtin-workflows/recon.md)
