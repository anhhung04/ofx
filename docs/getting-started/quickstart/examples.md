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
Run: `ofx flow run Hello World` (save as `hello-world.yml`). Expected: a single step that prints `Hello, OFX!`.

---

## Example 2: Scan a Target
```yaml
name: Scan Target
dispatch:
  inputs:
    target:
      description: Target to scan
      default: "localhost"
jobs:
  scan:
    name: Network Scan
    steps:
      - name: Run nmap
        run: nmap {{ inputs.target }}
```
Run: `ofx flow run Scan Target --input target=scanme.nmap.org`. Expected: `nmap` scan output with exit code 0. Ensure `nmap` is installed or add `run: {{ uv_install('nmap') }}` before the scan step.

---

## Example 3: Use a Secret
```yaml
name: API Request
jobs:
  api:
    name: Call API
    steps:
      - name: Make authenticated request
        run: curl -H "Authorization: Bearer {{ secrets.API_KEY }}" https://api.example.com
```
Prepare secret: `ofx secret set API_KEY`. Run: `ofx flow run API Request`. Expected: HTTP response body or failure message if the token is invalid.

---

## See Also
- [Quickstart Guide](../quickstart.md)