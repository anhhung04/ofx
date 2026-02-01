# Jobs

Jobs are the main building blocks of an OFX workflow. Each job contains one or more steps and can depend on other jobs. Jobs run in stages, either in parallel or sequentially based on dependencies.

---
## Job Structure
```yaml
jobs:
	recon:
		steps:
			- run: nmap {{ inputs.target }}
	exploit:
		needs: recon
		steps:
			- run: python exploit.py
```

---
## Job Fields
- `name`: (optional) Display name for the job
- `steps`: **Required.** List of steps to execute
- `needs`: (optional) List or string of job dependencies
- `run_if`: (optional) Conditional execution (alias: `if`)
- `strategy`: (optional) Matrix strategy for job expansion
- `envs`: (optional) Environment variables for all steps in the job
- `outputs`: (optional) Job outputs (template-resolved)
- `defaults`: (optional) Default run config overrides

---
## Parallel and Sequential Jobs
- Jobs without `needs:` run in parallel in the first stage
- Jobs with `needs:` run after their dependencies

---
## Example: Multiple Jobs
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
		needs: test
		steps:
			- run: ./deploy.sh
```

---
## Best Practices
- Use clear job names
- Use `needs:` to control execution order
- Group related steps in the same job

---
## See Also
- [Steps](steps.md)
- [Matrix Strategy](matrix-strategy.md)
- [Workflow Stages](../workflows/stages.md)