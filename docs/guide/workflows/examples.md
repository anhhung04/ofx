# Workflow Examples

This page provides practical OFX workflow examples for common red teaming, automation, and DevSecOps scenarios.

---

## Example 1: Simple Reconnaissance
```yaml
name: Web Recon
jobs:
	scan:
		steps:
			- run: nmap {{ inputs.target }}
```

---

## Example 2: Multi-Stage Exploitation
```yaml
name: Exploit Chain
jobs:
	recon:
		steps:
			- run: nmap {{ inputs.target }}
	exploit:
		needs: recon
		steps:
			- run: python exploit.py --target {{ inputs.target }}
	loot:
		needs: exploit
		steps:
			- run: ./loot.sh
```

---

## Example 3: Parallel Jobs
```yaml
jobs:
	scan1:
		steps:
			- run: nmap 10.0.0.1
	scan2:
		steps:
			- run: nmap 10.0.0.2
```

---

## Example 4: Using Outputs
```yaml
jobs:
	scan:
		steps:
			- run: nmap {{ inputs.target }}
				outputs:
					open_ports: "{{ step.stdout_lines }}"
	report:
		needs: scan
		steps:
			- run: echo "Ports: {{ jobs.scan.outputs.open_ports }}"
```

---

## Example 5: With Secrets
```yaml
jobs:
	api:
		steps:
			- run: curl -H "Authorization: Bearer {{ secrets.API_KEY }}" https://api.example.com
```

---

## Example 6: Interactive Debugging
```yaml
jobs:
	debug:
		steps:
			- run: bash
				interactive: true
				timeout: 10
```

---

## See Also
- [Workflow Stages](stages.md)
- [Dependencies](dependencies.md)