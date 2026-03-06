# API Reference

!!! abstract "The ofx.api module provides a comprehensive suite of tools for Red Teaming operations."
		Access built-in APIs for reconnaissance, exploitation, post-exploitation, evasion, and more. APIs are available in workflow templates and Python scripts.

---

## Overview

The `ofx.api` module exposes dozens of functions for:
- Reconnaissance
- Exploitation
- Post-exploitation
- Evasion
- Data exfiltration
- Lateral movement
- Persistence
- Payload generation
- Service enumeration

---

## Usage in Workflows

!!! example "Call API functions in templates"
		Use API functions in workflow steps via Jinja2:
		```yaml
		jobs:
			recon:
				steps:
					- run: echo "IP: {{ api.get_ip() }}"
					- run: echo "OS: {{ api.detect_os() }}"
		```

---

## Usage in Python Scripts

!!! example "Import and use APIs in scripts"
		```python
		from ofx.api import get_ip, detect_os
		ip = get_ip()
		os = detect_os()
		print(f"IP: {ip}, OS: {os}")
		```

---

## API Modules

| Module | Description |
|--------|-------------|
| `ofx.api.recon` | Reconnaissance tools |
| `ofx.api.exploitation` | Exploitation helpers |
| `ofx.api.post` | Post-exploitation runners |
| `ofx.api.evasion` | Evasion techniques |
| `ofx.api.exfil` | Data exfiltration |
| `ofx.api.lateral` | Lateral movement |
| `ofx.api.persistence` | Persistence helpers |
| `ofx.api.payloads` | Payload generation |
| `ofx.api.service` | Service enumeration |

---

## See Also

- [API CLI Reference](../cli/commands/api.md)
- [Templates Guide](../guide/templates.md)
- [Workflow Design](../guide/workflows.md)


