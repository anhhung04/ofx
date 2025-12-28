# Shodan API

Shodan (https://www.shodan.io) is a search engine for internet-connected devices. The OFX Shodan client automates authentication and asset searching for reconnaissance workflows.

---

## Features
- Automated credential management (config file or prompt)
- Search with Shodan dorks and retrieve results as URLs
- Supports pagination and custom resource types
- Integrates with OFX YAML workflows and Python scripts

---

## Setup
You need a Shodan account and API key. The client will prompt for these on first use, or you can provide them in a config file:

**Config file location:** `~/.local/share/ofx/config.ini`

```ini
[Shodan]
User = your@email.com
Token = your_shodan_api_key
```

---

## Usage in Python
```python
from ofx.api.search.shodan import Shodan

# Initialize (will prompt for credentials if not found)
shodan = Shodan()

# Search for assets with a Shodan dork
results = shodan.search('product:"nginx" country:"US"', pages=2)
for url in results:
		print(url)
```

**Parameters:**
- `dork` (str): Shodan query string (e.g., `port:8080 product:"nginx"`)
- `pages` (int): Number of result pages to fetch (default: 1)
- `resource` (str): 'host' for IP:port, or 'domain' for hostnames (default: 'host')

---

## Usage in OFX YAML Workflow
You can use the Shodan API in a workflow step:

```yaml
name: Shodan Recon Example
jobs:
	shodan_search:
		steps:
			- name: Search Shodan
				run: |
					from ofx.api.search.shodan import Shodan
					shodan = Shodan()
					results = shodan.search('product:"nginx" country:"US"', pages=1)
					for url in results:
							print(url)
				script:
				outputs:
					targets: "{{ step.stdout_lines }}"
```

---

## Example Queries
- `product:"nginx" country:"US"` — Find nginx servers in the US
- `port:443 product:"Apache"` — Apache servers on port 443
- `os:"Windows" city:"Beijing"` — Windows hosts in Beijing

---

## Tips
- Shodan dorks use a rich query language; see [Shodan Docs](https://help.shodan.io/en/latest/api.html) for syntax
- Always respect Shodan's API rate limits and your account's search credits
- Results are returned as a set of URLs (e.g., `https://1.2.3.4:443`)
- IPv6 addresses are wrapped in brackets (e.g., `https://[2606:4700:4700::1111]:443`)

---

## Error Handling
- If credentials are invalid, you will be prompted to re-enter them
- API errors and rate limits are logged to the console

---

## See Also
- [FOFA API](fofa.md)
- [ZoomEye API](zoomeye.md)