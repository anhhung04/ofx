# Hook Lifecycle

Hooks in OFX can be defined at the workflow, job, or step level. They execute in a specific order, allowing you to customize behavior at every stage.

---

## Hook Levels
- **Step-level:** Runs first, specific to a step
- **Job-level:** Runs if not overridden by step
- **Workflow-level:** Runs if not overridden by job or step

---

## Execution Order
1. Step-level hooks (if present)
2. Job-level hooks (if present and not overridden)
3. Workflow-level hooks (if present and not overridden)

---

## Available Hook Events
- `on_start`: Before execution
- `on_success`: On successful completion
- `on_failure`: On failure
- `on_error`: On error
- `on_end`: After all steps/jobs
- `on_line`: For each output line (steps only)
- `before_run`, `after_run`: Advanced, for custom runners

---

## Example: Step and Job Hooks
```yaml
jobs:
	scan:
		hooks:
			on_start:
				run: echo "Job started"
				language: shell
		steps:
			- run: nmap ${{ inputs.target }}
				hooks:
					on_success:
						run: echo "Step succeeded"
						language: shell
```

---

## See Also
- [Hooks Guide](index.md)