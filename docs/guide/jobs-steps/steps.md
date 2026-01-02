# Steps

Steps are the smallest unit of execution in an OFX workflow. Each step runs a command, script, or code block, and can have its own environment, outputs, and error handling.

---

## Step Syntax
```yaml
jobs:
	example:
		steps:
			- name: Run Script
				run: ./myscript.sh
				env:
					VAR: value
				timeout: 10
				outputs:
					result: "{{ step.stdout }}"
				continue_on_error: true
```

---

## Step Fields
- `name`: (optional) Description of the step
- `run`: Command, script, or code to execute
- `language`: (optional) Language for code blocks (e.g., python)
- `env`: (optional) Environment variables
- `timeout`: (optional) Max time in minutes
- `outputs`: (optional) Exported values from this step
- `continue_on_error`: (optional) Continue even if this step fails
- `run_if`: (optional) Conditional execution (e.g., `failure()`)

---

## Advanced Usage
- Use `script:` to run inline Python code
- Use `outputs:` to pass data between steps and jobs
- Use `run_if:` for conditional logic (see [Hooks & Conditions](../hooks/index.md))

---

## Example: Python Step
```yaml
steps:
	- name: Calculate
		run: |
			result = 2 + 2
			print(f"Result: {result}")
		script:
		outputs:
			calc: "{{ step.stdout }}"
```

---

## See Also
- [Jobs](jobs.md)
- [Outputs](outputs.md)