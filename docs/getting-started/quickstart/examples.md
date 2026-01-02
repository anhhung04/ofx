# Quickstart Examples

Here are simple OFX workflow examples to get you started quickly.

---

## Example 1: Hello World
```yaml
name: Hello World
jobs:
  hello:
    name: Say Hello
    steps:
      - name: Print greeting
        run: echo "Hello, OFX!"
```

---

## Example 2: Scan a Target
```yaml
name: Scan Target
inputs:
  target:
    description: Target to scan
    default: "localhost"
jobs:
  scan:
    name: Network Scan
    steps:
      - name: Run nmap
        run: nmap ${{ inputs.target }}
```

---

## Example 3: Use a Secret
```yaml
name: API Request
jobs:
  api:
    name: Call API
    steps:
      - name: Make authenticated request
        run: curl -H "Authorization: Bearer ${{ secrets.API_KEY }}" https://api.example.com
```

---

## See Also
- [Quickstart Guide](index.md)