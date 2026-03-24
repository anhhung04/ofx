# Validate

Validate workflow configuration with detailed diagnostics.

---

## Usage

```bash
ofx flow validate <workflow> [options]
ofx flow validate --all [--check-tasks]
```

---

## Description

Validates workflow files and reports:

- Schema and YAML syntax validity
- Structure summary (jobs, steps, tags, triggers)
- Task reference verification (with `--check-tasks`)
- Dependency warnings (missing job refs, empty steps)

---

## Arguments

- `workflow` — Workflow name or path. Supports bare names (recursive search), category paths, and file paths.

## Options

| Option | Description |
|---|---|
| `--all` | Validate all discoverable workflows (builtin + user + collections) |
| `--check-tasks` | Verify that task references match registered task wrappers |

---

## Examples

```bash
# Validate a single workflow
ofx flow validate subdomain-recon

# Validate all workflows
ofx flow validate --all

# Validate all with task reference checking
ofx flow validate --all --check-tasks
```

### Single workflow output

Shows a detailed panel with jobs, steps, tags, triggers, and task ref counts.

### Bulk output

Shows a summary table with pass/warn/fail status per workflow.

---

## Also available via doctor

```bash
ofx doctor workflows --check-tasks
```

---

## See Also

- [Info Command](info.md)
- [Run Command](run.md)
- [Visualize Command](visualize.md)
