# Validate

Validate workflow configuration with detailed diagnostics.

---

## Usage

```bash
ofx flow validate <workflow> [options]
ofx flow validate --all
```

---

## Description

Validates workflow files and reports:

- Schema and YAML syntax validity
- Structure summary (jobs, steps, tags, triggers)
- Dependency warnings (missing job refs, empty steps)

---

## Arguments

- `workflow` — Workflow name or path. Supports bare names (recursive search), category paths, and file paths.

## Options

| Option | Description |
|---|---|
| `--all` | Validate all discoverable workflows (builtin + user + collections) |

---

## Examples

```bash
# Validate a single workflow
ofx flow validate subdomain-recon

# Validate all workflows
ofx flow validate --all
```

### Single workflow output

Shows a detailed panel with jobs, steps, tags, and triggers.

### Bulk output

Shows a summary table with pass/warn/fail status per workflow.

---

## Also available via doctor

```bash
ofx doctor workflows
```

---

## See Also

- [Info Command](info.md)
- [Run Command](run.md)
- [Visualize Command](visualize.md)
