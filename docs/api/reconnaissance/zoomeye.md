# ZoomEye API

ZoomEye (https://www.zoomeye.org) is a search engine for internet-connected assets. The OFX ZoomEye client automates authentication and asset searching for reconnaissance workflows.

---

## Features
- Automated credential management (config file or prompt)
- Search with ZoomEye dorks and retrieve results as URLs
- Supports pagination and custom resource types
- Integrates with OFX YAML workflows and Python scripts

---

## Setup
You need a ZoomEye account and API key. The client will prompt for these on first use, or you can provide them in a config file:

**Config file location:** `~/.local/share/ofx/config.ini`

```ini
[ZoomEye]
User = your@email.com
Token = your_zoomeye_api_key
```

---

## Usage in Python
```python
from ofx.api.search.zoomeye import ZoomEye

# Initialize (will prompt for credentials if not found)
zoomeye = ZoomEye()

# Search for assets with a ZoomEye dork
results = zoomeye.search('app:"nginx" && country:"US"', pages=2)
for url in results:
		print(url)
```

**Parameters:**
- `dork` (str): ZoomEye query string (e.g., `port:8080 && app:"nginx"`)
- `pages` (int): Number of result pages to fetch (default: 1)
- `resource` (str): 'host' for IP:port, or 'domain' for hostnames (default: 'host')

---

## Usage in OFX YAML Workflow
You can use the ZoomEye API in a workflow step:

```yaml
name: ZoomEye Recon Example
jobs:
	zoomeye_search:
		steps:
			- name: Search ZoomEye
				run: |
					from ofx.api.search.zoomeye import ZoomEye
					zoomeye = ZoomEye()
					results = zoomeye.search('app:"nginx" && country:"US"', pages=1)
					for url in results:
							print(url)
				script:
				outputs:
					targets: "{{ step.stdout_lines }}"
```

---

## Example Queries
- `app:"nginx" && country:"US"` — Find nginx servers in the US
- `port:443 && app:"Apache"` — Apache servers on port 443
- `os:"Windows" && city:"Beijing"` — Windows hosts in Beijing

---

## Tips
- ZoomEye dorks use a rich query language; see [ZoomEye Docs](https://www.zoomeye.org/doc) for syntax
- Always respect ZoomEye's API rate limits and your account's search credits
- Results are returned as a set of URLs (e.g., `https://1.2.3.4:443`)
- IPv6 addresses are wrapped in brackets (e.g., `https://[2606:4700:4700::1111]:443`)

---

## Error Handling
- If credentials are invalid, you will be prompted to re-enter them
- API errors and rate limits are logged to the console

---

## See Also
- [FOFA API](fofa.md)
- [Shodan API](shodan.md)