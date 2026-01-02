# Data Directory Structure

The data directory in OFX stores reusable assets, payloads, templates, and other resources used by workflows and custom connectors.

---

## Structure
Typical layout:
```
src/ofx/data/
	shellcode/
	site/
	webshell/
	...
```

---

## How to Use
- Reference files in the data directory from workflow steps
- Use in custom connectors to load payloads or templates

---

## Example: Using a Payload
```yaml
steps:
	- name: Use Payload
		run: |
			with open('src/ofx/data/shellcode/payload.bin', 'rb') as f:
					data = f.read()
			# Use data in exploit
		script:
```

---

## Best Practices
- Organize data by type (e.g., shellcode, webshells)
- Document the purpose of each file
- Avoid storing secrets in the data directory

---

## See Also
- [Custom Connectors](custom-connectors.md)