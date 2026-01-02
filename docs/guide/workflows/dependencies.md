# Workflow Dependencies

Dependencies control the execution order of jobs in an OFX workflow. Use the `needs:` field to specify which jobs must complete before a job can start.

---

## Syntax
```yaml
jobs:
	build:
		steps:
			- run: make
	test:
		needs: build
		steps:
			- run: pytest
	deploy:
		needs: [test]
		steps:
			- run: ./deploy.sh
```

---

## How It Works
- Jobs without `needs:` run in the first stage
- Jobs with `needs:` wait for their dependencies
- You can specify a single job or a list of jobs

---

## Example: Multiple Dependencies
```yaml
jobs:
	setup:
		steps:
			- run: ./setup.sh
	scan:
		needs: setup
		steps:
			- run: nmap {{ inputs.target }}
	exploit:
		needs: [setup, scan]
		steps:
			- run: python exploit.py
```

---

## Best Practices
- Use dependencies to enforce correct order and avoid race conditions
- Avoid circular dependencies (will cause errors)
- Use dependencies to control parallelism and resource usage

---

## See Also
- [Workflow Stages](stages.md)
- [Workflow Examples](examples.md)