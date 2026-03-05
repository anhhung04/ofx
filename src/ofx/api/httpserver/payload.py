"""Payload HTTP server implementation."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from pathlib import Path

from ofx.api._compat import get_logger
from ofx.api.httpserver.server_base import BaseServerFacade

logger = get_logger()


def build_payload_handler(
    payload_path: Path | None,
    payloads: dict[str, bytes],
    hits: dict[str, int],
) -> type[BaseHTTPRequestHandler]:
    """Create a request handler with injected payload dependencies."""

    class PayloadRequestHandler(BaseHTTPRequestHandler):
        """Custom HTTP request handler for PayloadServer.

        Handles GET and POST requests for payload delivery and logging.
        """

        def __init__(self, *args: object, **kwargs: object) -> None:
            self._payload_path = payload_path
            self._payloads = payloads
            self._hits = hits
            super().__init__(*args, **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            print(
                f"{self.address_string()} - - [{self.log_date_time_string()}] {format % args}\n"
            )

        def do_GET(self) -> None:
            """Handle GET requests for payload delivery.

            Serves the payload file if it exists, otherwise returns 404.
            """
            if self.path == "/payload":
                if self._payload_path and self._payload_path.exists():
                    self.send_response(200)
                    self.send_header("Content-type", "application/octet-stream")
                    self.send_header(
                        "Content-Disposition",
                        f'attachment; filename="{self._payload_path.name}"',
                    )
                    self.end_headers()

                    with open(self._payload_path, "rb") as f:
                        self.wfile.write(f.read())
                    logger.info(f"Payload served to {self.client_address[0]}")
                else:
                    self.send_error(404, "Payload not found")
            else:
                if self.path in self._payloads:
                    self.send_response(200)
                    self.send_header("Content-type", "application/octet-stream")
                    self.end_headers()
                    self.wfile.write(self._payloads[self.path])

                    self._hits[self.path] = self._hits.get(self.path, 0) + 1

                    logger.info(
                        f"Payload {self.path} served to {self.client_address[0]}"
                    )
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

    return PayloadRequestHandler


class PayloadServer(BaseServerFacade):
    """HTTP server for delivering payloads and collecting data.

    Provides an HTTP server specifically designed for delivering malicious
    payloads and collecting data from compromised systems. Supports both
    HTTP and HTTPS protocols.

    Example:
        >>> server = PayloadServer(host='0.0.0.0', port=8080, payload_path='/path/to/payload.exe')
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
        super().__init__(
            host=host,
            port=port,
            is_ipv6=is_ipv6,
            use_https=use_https,
            certfile=certfile,
        )

        self.payload_path = Path(payload_path) if payload_path else None
        self.payload_path.mkdir(
            parents=True, exist_ok=True
        ) if self.payload_path else None
        self.payloads: dict[str, bytes] = {}  # path -> content
        self.hits: dict[str, int] = {}  # path -> count

        if self.payload_path and not self.payload_path.exists():
            logger.warning(f"Payload file {self.payload_path} does not exist")

        handler = build_payload_handler(self.payload_path, self.payloads, self.hits)
        self._server = self._create_server(handler)

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
