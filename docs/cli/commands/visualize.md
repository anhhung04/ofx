# flow visualize

Visualize workflow dependencies and execution flow.

## Usage

```bash
ofx flow visualize <workflow> [options]
```

## Description

Creates visual representations of workflow structure, dependencies, and execution stages. Displays:

- Workflow dependency graph
- Execution stages
- Job relationships
- Parallel execution opportunities

## Arguments

- `workflow` - Workflow file or name to visualize

## Options

- `--format <format>` - Output format: `terminal` (default), `dot`, `json`
- `--output <file>` - Save visualization to file
- `--detailed` - Show detailed job information

## Examples

### Basic visualization

```bash
ofx flow visualize scan-workflow.yaml
```

### Export to GraphViz DOT format

```bash
ofx flow visualize attack-chain --format dot --output workflow.dot
```

### Detailed view

```bash
ofx flow visualize complex-workflow --detailed
```

## Visualization Output

The terminal visualization shows:

1. **Workflow Overview**
   - Name, description
   - Total jobs, execution stages
   - Est. parallel efficiency

2. **Workflow Statistics**
   - Job count, stage count
   - Dependencies, outputs
   - Hooks, conditionals

3. **Dependency Graph**
   - ASCII art representation
   - Job boxes with dependencies
   - Stage grouping
   - Edge connections

4. **Job Specifications**
   - Detailed job information
   - Steps, dependencies
   - Outputs, hooks

## Graph Formats

### Terminal (Default)
ASCII art graph displayed in terminal with colors and formatting.

### DOT Format
GraphViz DOT language for rendering with `dot` command:

```bash
ofx flow visualize workflow.yaml --format dot --output graph.dot
dot -Tpng graph.dot -o graph.png
```

### JSON Format
Machine-readable JSON structure:

```json
{
  "stages": [[...]],
  "dependencies": {...},
  "jobs": {...}
}
```

## See Also

- [flow run](run.md)
- [flow validate](validate.md)
- [Workflow Dependencies](../../guide/workflows/dependencies.md)
