# Quickstart Examples

Here are simple OFX workflow examples to get you started quickly.

---

## Example 1: Hello World
```yaml
name: Hello World
jobs:
	hello:
		steps:
			- run: echo "Hello, OFX!"
```

---

## Example 2: Scan a Target
```yaml
name: Scan Target
inputs:
	target: "localhost"
jobs:
	scan:
		steps:
			- run: nmap {{ inputs.target }}
```

---

## Example 3: Use a Secret
```yaml
jobs:
	api:
		steps:
			- run: curl -H "Authorization: Bearer {{ secrets.API_KEY }}" https://api.example.com
```

---

## See Also
- [Quickstart Guide](index.md)