# Outputs

Outputs allow you to pass data from one step or job to another in an OFX workflow. Use outputs to chain results, share variables, and build dynamic workflows.

---

## Step Outputs
Define outputs in a step to export values:
```yaml
steps:
	- name: Scan
		run: nmap ${{ inputs.target }}
		outputs:
			open_ports: "${{ step.stdout_lines }}"
```

**Access in later steps:**
```yaml
run: echo "Ports: {{ steps.0.outputs.open_ports }}"
```

---

## Job Outputs
You can also export outputs from a job:
```yaml
jobs:
	scan:
		steps:
			- run: ...
				outputs:
					result: "${{ step.stdout }}"
		outputs:
			scan_result: "{{ steps.0.outputs.result }}"
```

**Access in other jobs:**
```yaml
run: echo "Scan: ${{ jobs.scan.outputs.scan_result }}"
```

---

## Output Types
- `stdout`: Raw output as a string
- `stdout_lines`: Output as a list of lines
- Custom parsing with Jinja2 filters

---

## Best Practices
- Name outputs clearly for easy reference
- Use outputs to avoid repeating work

---

## See Also
- [Steps](steps.md)
- [Jobs](jobs.md)