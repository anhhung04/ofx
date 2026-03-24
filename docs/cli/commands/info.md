# Info

Display detailed information about a workflow including inputs, execution plan, and outputs.

---

## Usage

```bash
ofx flow info <workflow> [options]
```

---

## Description

Shows a comprehensive overview of a workflow:

- **Overview panel** — name, description, tags, job/step counts, triggers, tools
- **Inputs table** — dispatch inputs with types, defaults, and aliases
- **Execution plan** — topologically sorted stages showing job dependencies, cloud/matrix badges
- **Job outputs** — all declared job outputs with their source expressions

---

## Arguments

- `workflow` — Workflow name or path. Supports bare names (recursive search), category paths (`recon/subdomain-recon`), and file paths.

## Options

| Option | Short | Description |
|---|---|---|
| `--detailed` | `-d` | Show step-level details inside each job (step names, types, timeouts) |

---

## Examples

```bash
# Basic info
ofx flow info subdomain-recon

# Detailed view with step-level breakdown
ofx flow info host-scan --detailed

# Using category path
ofx flow info recon/subdomain-recon
```

---

## See Also

- [List Command](list.md)
- [Visualize Command](visualize.md)
- [Run Command](run.md)
