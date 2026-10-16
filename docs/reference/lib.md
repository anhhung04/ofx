# API Reference

!!! abstract "The ofx.lib module provides a comprehensive suite of tools for Red Teaming operations."
		Access built-in APIs for reconnaissance, exploitation, post-exploitation, evasion, and more. APIs are available in workflow templates and Python scripts.

---

## Overview

The `ofx.lib` module exposes dozens of functions for:
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
					- module: shell
					  with:
					    cmd: echo "IP: {{ api.get_ip() }}"
					- module: shell
					  with:
					    cmd: echo "OS: {{ api.detect_os() }}"
		```

---

## Usage in Python Scripts

!!! example "Import and use APIs in scripts"
		```python
		from ofx.lib import get_ip, detect_os
		ip = get_ip()
		os = detect_os()
		print(f"IP: {ip}, OS: {os}")
		```

---

## API Modules

| Module | Description |
|--------|-------------|
| `ofx.lib.recon` | Reconnaissance tools |
| `ofx.lib.exploitation` | Exploitation helpers |
| `ofx.lib.post` | Post-exploitation runners |
| `ofx.lib.evasion` | Evasion techniques |
| `ofx.lib.exfil` | Data exfiltration |
| `ofx.lib.lateral` | Lateral movement |
| `ofx.lib.persistence` | Persistence helpers |
| `ofx.lib.payloads` | Payload generation |
| `ofx.lib.service` | Service enumeration |

---

## See Also

- [API CLI Reference](../cli/commands/api.md)
- [Templates Guide](../guide/templates.md)
- [Workflow Design](../guide/workflows.md)


