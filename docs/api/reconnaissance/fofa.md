# FOFA API

FOFA (https://fofa.info) is a powerful search engine for internet-connected assets. The OFX FOFA client automates authentication, credential management, and asset searching for red teaming and reconnaissance workflows.

---

## Features
- Automated credential management (config file or prompt)
- Search with FOFA dorks and retrieve results as URLs
- Supports pagination and custom resource types
- Integrates with OFX YAML workflows and Python scripts

---

## Setup
You need a FOFA account and API key. The client will prompt for these on first use, or you can provide them in a config file:

**Config file location:** `~/.local/share/ofx/config.ini`

```ini
[Fofa]
User = your@email.com
Token = your_fofa_api_key
```

---

## Usage in Python
```python
from ofx.api.search.fofa import Fofa

# Initialize (will prompt for credentials if not found)
fofa = Fofa()

# Search for assets with a FOFA dork
results = fofa.search('title="login" && country="US"', pages=2)
for url in results:
		print(url)
```

**Parameters:**
- `dork` (str): FOFA query string (e.g., `port=8080 && protocol="http"`)
- `pages` (int): Number of result pages to fetch (default: 1)
- `resource` (str): 'host' for IP:port, or 'domain' for hostnames (default: 'host')

---

## Usage in OFX YAML Workflow
You can use the FOFA API in a workflow step:

```yaml
name: FOFA Recon Example
jobs:
	fofa_search:
				steps:
					- name: Search FOFA
						script: |
							from ofx.api.search.fofa import Fofa
							fofa = Fofa()
							results = fofa.search('app="Apache" && country="CN"', pages=1)
							for url in results:
								print(url)
						outputs:
							targets: "{{ step.stdout_lines }}"
```

---

## Example Queries
- `title="admin" && country="US"` — Find admin panels in the US
- `app="Apache" && port=80` — Apache servers on port 80
- `protocol="https" && cert.subject.CN="*.gov"` — HTTPS .gov domains

---

## Tips
- FOFA dorks use a rich query language; see [FOFA Docs](https://fofa.info/static_pages/api_help) for syntax
- Always respect FOFA's API rate limits and your account's search credits
- Results are returned as a set of URLs (e.g., `https://1.2.3.4:443`)
- IPv6 addresses are wrapped in brackets (e.g., `https://[2606:4700:4700::1111]:443`)

---

## Error Handling
- If credentials are invalid, you will be prompted to re-enter them
- API errors and rate limits are logged to the console

---

## See Also
- [Shodan API](shodan.md)
- [ZoomEye API](zoomeye.md)