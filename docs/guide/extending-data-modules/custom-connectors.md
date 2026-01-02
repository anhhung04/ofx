# Custom Connectors

Custom connectors allow you to extend OFX with your own data sources, APIs, or integrations. Use them to add new asset types, fetch data from external systems, or enrich workflow context.

---

## Why Use Custom Connectors?
- Integrate with internal asset inventories or ticketing systems
- Pull data from third-party APIs
- Normalize and enrich workflow inputs

---

## How to Implement
1. Create a new Python module in `src/ofx/api/connectors/` (or similar)
2. Define a class with methods for fetching or transforming data
3. Register your connector in the workflow or as a step

---

## Example: Custom Asset Fetcher
```python
# src/ofx/api/connectors/myassets.py
class MyAssetConnector:
		def fetch_assets(self, query):
				# Connect to internal API
				...
				return ["host1", "host2"]
```

**YAML usage:**
```yaml
steps:
	- name: Fetch Assets
		run: |
			from ofx.api.connectors.myassets import MyAssetConnector
			assets = MyAssetConnector().fetch_assets("prod")
			for host in assets:
					print(host)
		script:
		outputs:
			hosts: "${{ step.stdout_lines }}"
```

---

## Best Practices
- Keep connector logic modular and reusable
- Handle API errors and timeouts gracefully
- Document required environment variables or secrets

---

## See Also
- [Data Directory](data-directory.md)