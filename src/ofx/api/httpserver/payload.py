"""Payload HTTP server implementation."""

from __future__ import annotations

import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from ofx.api.httpserver.base import PHTTPServer
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class PayloadRequestHandler(BaseHTTPRequestHandler):
    """Custom HTTP request handler for PayloadServer.

    Handles GET and POST requests for payload delivery and logging.
    """

    def log_message(self, format: str, *args: object) -> None:
        logger.info(
            f"{self.address_string()} - - [{self.log_date_time_string()}] {format % args}\n"
        )

    def do_GET(self) -> None:
        """Handle GET requests for payload delivery.

        Serves the payload file if it exists, otherwise returns 404.
        """
        if self.path == "/payload":
            payload_path = getattr(self.server, "payload_path", None)
            if payload_path and payload_path.exists():
                self.send_response(200)
                self.send_header("Content-type", "application/octet-stream")
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{payload_path.name}"'
                )
                self.end_headers()

                with open(payload_path, "rb") as f:
                    self.wfile.write(f.read())
                logger.info(f"Payload served to {self.client_address[0]}")
            else:
                self.send_error(404, "Payload not found")
        else:
            # Check if path matches a registered payload
            server = getattr(self, "server", None)
            if server and hasattr(server, "payloads") and self.path in server.payloads:
                self.send_response(200)
                self.send_header("Content-type", "application/octet-stream")
                self.end_headers()
                self.wfile.write(server.payloads[self.path])

                # Track hits
                if hasattr(server, "hits"):
                    server.hits[self.path] = server.hits.get(self.path, 0) + 1

                logger.info(f"Payload {self.path} served to {self.client_address[0]}")
            else:
                self.send_error(404, "Not found")

    def do_POST(self) -> None:
        """Handle POST requests for logging or data collection.

        Logs POST data and returns success response.
        """
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b""

        logger.info(
            f"POST request from {self.client_address[0]}: {post_data.decode('utf-8', errors='ignore')}"
        )

        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")


class PayloadServer:
    """HTTP server for delivering payloads and collecting data.

    Provides an HTTP server specifically designed for delivering malicious
    payloads and collecting data from compromised systems. Supports both
    HTTP and HTTPS protocols.

    Example:
        >>> server = PayloadServer(bind_ip='0.0.0.0', bind_port=8080, payload_path='/path/to/payload.exe')
        >>> server.start()
        >>> # Server is now serving payload at http://0.0.0.0:8080/payload
        >>> server.stop()
    """

    def __init__(
        self,
        port: int = 8080,
        host: str = "0.0.0.0",
        payload_path: str | Path | None = None,
        is_ipv6: bool = False,
        use_https: bool = False,
        certfile: Path | None = None,
    ):
        """Initialize PayloadServer.

        Args:
            port: Server port (default: 8080)
            host: IP address to bind to (default: '0.0.0.0')
            payload_path: Path to the payload file to serve
            is_ipv6: Use IPv6 addressing (default: False)
            use_https: Enable HTTPS with SSL (default: False)
            certfile: Path to SSL certificate file (auto-generated if None)
        """
        self.port = port
        self.host = host
        self.payload_path = Path(payload_path) if payload_path else None
        self.is_ipv6 = is_ipv6
        self.use_https = use_https
        self.certfile = certfile
        self.payloads = {}  # path -> content
        self.hits = {}  # path -> count

        if self.payload_path and not self.payload_path.exists():
            logger.warning(f"Payload file {self.payload_path} does not exist")

        self.server = PHTTPServer(
            bind_ip=host,
            bind_port=port,
            is_ipv6=is_ipv6,
            use_https=use_https,
            certfile=certfile,
            requestHandler=PayloadRequestHandler,
        )

        # Store payload path in server instance for handler access
        setattr(self.server, "payload_path", self.payload_path)

    def add_payload(
        self, path: str, content: str | None = None, file: str | Path | None = None
    ) -> None:
        """Add a payload to serve.

        Args:
            path: URL path to serve the payload at
            content: String content to serve
            file: Path to file to serve (alternative to content)
        """
        if content is not None:
            self.payloads[path] = content.encode("utf-8")
        elif file is not None:
            file_path = Path(file)
            if file_path.exists():
                with open(file_path, "rb") as f:
                    self.payloads[path] = f.read()
            else:
                raise FileNotFoundError(f"Payload file not found: {file}")
        else:
            raise ValueError("Either content or file must be provided")

    def get_hits(self, path: str) -> int:
        """Get the number of hits for a payload path.

        Args:
            path: URL path of the payload

        Returns:
            Number of times the payload has been accessed
        """
        return self.hits.get(path, 0)

    def remove_payload(self, path: str) -> None:
        """Remove a payload from the server.

        Args:
            path: URL path of the payload to remove
        """
        if path in self.payloads:
            del self.payloads[path]
        if path in self.hits:
            del self.hits[path]

    def start(self, daemon: bool = False) -> None:
        """Start the HTTP server in a background thread.

        Args:
            daemon: Run as daemon thread (default: False)

        Example:
            >>> server.start()
            [INFO] Starting httpd on http://0.0.0.0:8080
        """
        self.server.start(daemon=daemon)

    def stop(self) -> None:
        """Stop the HTTP server and release resources.

        Example:
            >>> server.stop()
            [INFO] Stop httpd server on http://0.0.0.0:8080
        """
        self.server.stop()

    def pause(self) -> None:
        """Pause the HTTP server temporarily.

        Example:
            >>> server.pause()
            >>> # Server stops accepting requests
        """
        self.server.pause()

    def resume(self) -> None:
        """Resume a paused HTTP server.

        Example:
            >>> server.resume()
            >>> # Server resumes accepting requests
        """
        self.server.resume()

    @property
    def url(self) -> str:
        """Get the server URL.

        Returns:
            Server URL including protocol, IP, and port
        """
        return self.server.url

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running.

        Returns:
            True if server is running, False otherwise
        """
        return self.server.server_started
