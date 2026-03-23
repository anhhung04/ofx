# List Workflows

List available workflows across local/user directories, built-in OFX workflows, and installed collection workflows.

---

## Usage

```bash
ofx flow list
```

---

## What it lists

`ofx flow list` aggregates workflows from:

- Current working directory
- `~/.ofx/workflows`
- Built-in packaged workflows
- Installed collections (`ofx flow collection add ...`)

Output columns:

- **Workflow**: workflow name (file stem)
- **Source**: `user`, `builtin`, or `collection:<name>`
- **Path**: full workflow file path

---

## Examples

```bash
# List everything available to the resolver
ofx flow list

# Then run one directly
ofx flow run domain-recon --input target=example.com
```

---

## See Also

- [Run Command](run.md)
- [Collection Command](collection.md)
- [Built-in Workflows Guide](../../guide/builtin-workflows.md)
