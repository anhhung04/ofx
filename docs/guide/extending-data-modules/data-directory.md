# Data Directory Structure

The data directory in OFX stores reusable assets, payloads, templates, and other resources used by workflows and custom connectors. You can extend it with user data under `~/.ofx/`.

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

User extension layout:
```
~/.ofx/
	exploits/
	shellcode/connectors/
	webshell/connectors/
```

---

## How to Use
- Reference built-in files via `DATA_DIR`
- Store user extensions in `~/.ofx/` subdirectories
- Use in custom connectors to load payloads or templates

---

## Example: Using a Payload
```yaml
steps:
	- name: Use Payload
		run: |
			from ofx.settings import DATA_DIR
			with open(DATA_DIR / 'shellcode' / 'payload.bin', 'rb') as f:
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
