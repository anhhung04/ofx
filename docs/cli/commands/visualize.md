# Visualize

Visualize workflow dependencies and execution flow as a DAG.

---

## Usage

```bash
ofx flow visualize <workflow> [options]
```

---

## Description

Creates visual representations of workflow structure and dependencies. Displays:

- Statistics panel (jobs, steps, stages, max parallelism, dependencies)
- Stage-by-stage DAG with job boxes showing dependencies and badges (cloud, matrix)
- Detailed mode adds step-level breakdown inside each box

---

## Arguments

- `workflow` — Workflow name or path. Supports bare names (recursive search), category paths, and file paths.

## Options

| Option | Short | Description |
|---|---|---|
| `--format <format>` | `-f` | Output format: `terminal` (default), `dot`, `json` |
| `--output <file>` | `-o` | Save visualization to file instead of printing |
| `--detailed` | `-d` | Show step-level information in job boxes |

---

## Examples

### Terminal visualization (default)

```bash
ofx flow visualize subdomain-recon
```

### Detailed view with steps

```bash
ofx flow visualize host-scan --detailed
```

### Export to GraphViz DOT

```bash
ofx flow visualize host-scan --format dot --output workflow.dot
dot -Tpng workflow.dot -o workflow.png
```

### Export as JSON

```bash
ofx flow visualize host-scan --format json --output dag.json
```

---

## Output Formats

### Terminal (default)

ASCII art DAG with Rich formatting, showing:
- Stage headers with parallel indicators
- Job boxes with name, step count, dependencies
- Cloud (☁) and matrix (⊞) badges
- Connector arrows between stages

### DOT

GraphViz DOT language with stage subgraphs and dependency edges. Render with:

```bash
dot -Tpng graph.dot -o graph.png
dot -Tsvg graph.dot -o graph.svg
```

### JSON

Machine-readable structure with stages, jobs, and dependency edges.

---

## See Also

- [Info Command](info.md)
- [Run Command](run.md)
- [Validate Command](validate.md)
