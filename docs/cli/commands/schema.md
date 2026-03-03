# flow schema

Inspect OFX data model schemas for workflows, jobs, and steps.

## Usage

```bash
ofx flow schema <subcommand> [options]
```

---

## Subcommands

### schema

Export the OFX workflow model schema as a JSON file.

```bash
ofx flow schema schema [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-o, --output <path>` | Output file path for the JSON schema (default: `workflow_schema.json` in data dir) |

**Example:**

```bash
ofx flow schema schema -o workflow_schema.json
```

---

### flow

Display the Workflow model schema as a rich, human-readable tree in the terminal.

```bash
ofx flow schema flow
```

Shows all properties of the top-level `Workflow` model including types, defaults, and descriptions.

---

### job

Display the Job model schema as a rich, human-readable tree.

```bash
ofx flow schema job
```

Shows all properties of the `Job` model including matrix strategy, cloud config, environment, and step definitions.

---

### step

Display the Step model schema as a rich, human-readable tree.

```bash
ofx flow schema step
```

Shows all properties of the `Step` model including run/script/uses, retry, timeout, and output options.

---

## Examples

### Export full JSON schema

```bash
ofx flow schema schema -o /tmp/ofx-schema.json
cat /tmp/ofx-schema.json | python -m json.tool
```

### Browse model structure interactively

```bash
# See workflow-level fields
ofx flow schema flow

# Drill into job configuration
ofx flow schema job

# Inspect step options
ofx flow schema step
```

---

## See Also

- [Workflows Guide](../../guide/workflows.md) — Workflow syntax and structure
- [Jobs & Steps](../../guide/jobs-steps.md) — Job and step configuration
- [flow validate](validate.md) — Validate workflow files against the schema
