# CLI Reference

!!! abstract "Internal structure and usage of OFX CLI commands."
	For detailed usage, see the [CLI Guide](../cli/commands.md).

---

## Overview

OFX CLI provides commands for:
- Workflow execution
- Cloud management
- Project setup
- Session handling
- Secret management
- Documentation serving

---

## Command Structure

| Command | Description |
|---------|-------------|
| `ofx flow run` | Run workflows |
| `ofx flow validate` | Validate workflow syntax |
| `ofx flow visualize` | Visualize workflow DAG |
| `ofx flow collection` | Manage workflow collections |
| `ofx cloud` | Manage cloud profiles and instances |
| `ofx session` | Manage detached sessions |
| `ofx secret` | Manage secrets |
| `ofx docs` | Serve documentation |

---

## Example Usage

!!! example "Run a workflow"
	```bash
	ofx flow run my-workflow.yml --input target=example.com
	```

!!! example "Validate a workflow"
	```bash
	ofx flow validate my-workflow.yml
	```

!!! example "Visualize workflow DAG"
	```bash
	ofx flow visualize my-workflow.yml --format png
	```

---

## See Also

- [CLI Guide](../cli/commands.md)
- [Workflow Design](../guide/workflows.md)
- [Collections](../guide/collections.md)


