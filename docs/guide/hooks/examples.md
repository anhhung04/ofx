# Hook Examples

Hooks let you run custom code at key points in your workflow, job, or step lifecycle. Here are practical examples for common use cases.

---

## Example 1: Workflow Start Notification
```yaml
hooks:
	on_start:
		run: echo "Workflow started at $(date)"
		language: shell
```

---

## Example 2: Job Failure Alert
```yaml
jobs:
	exploit:
		hooks:
			on_failure:
				run: |
					import requests
					requests.post("https://alerts.local/webhook", json={"status": "fail"})
				script:
		steps:
			- run: python exploit.py
```

---

## Example 3: Step Output Processing
```yaml
steps:
	- run: nmap {{ inputs.target }}
		hooks:
			on_line:
				run: print("Line:", line)
				script:
```

---

## Example 4: Cleanup on End
```yaml
hooks:
	on_end:
		run: rm -rf /tmp/ofx*
		language: shell
```

---

## See Also
- [Hooks Guide](index.md)