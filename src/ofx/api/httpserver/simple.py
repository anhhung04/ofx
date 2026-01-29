"""Simple HTTP server implementation."""

from __future__ import annotations

import logging
import os
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

from ofx.api.httpserver.base import PHTTPServer
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class SimpleHTTPHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler for SimpleHTTPServer.

    Extends SimpleHTTPRequestHandler to provide custom logging
    and directory listing behavior.
    """

    def log_message(self, format: str, *args: object) -> None:
        logger.info(
            f"{self.address_string()} - - [{self.log_date_time_string()}] {format % args}\n"
        )

    def list_directory(self, path: str) -> bytes | None:
        """Override directory listing to disable it.

        Returns None to prevent directory listing, which is a security
        best practice for simple file servers.

        Args:
            path: Directory path being requested

        Returns:
            None to disable directory listing
        """
        self.send_error(403, "Directory listing not allowed")
        return None


class SimpleHTTPServer:
    """Simple HTTP file server with directory serving capabilities.

    Provides a basic HTTP server for serving static files from a specified
    directory. Supports both HTTP and HTTPS protocols with automatic
    certificate generation for SSL.

    Example:
        >>> server = SimpleHTTPServer(bind_ip='0.0.0.0', bind_port=8080, directory='/var/www')
        >>> server.start()
        >>> # Server is now serving files from /var/www at http://0.0.0.0:8080
        >>> server.stop()
    """

    def __init__(
        self,
        port: int = 8000,
        directory: str | Path | None = None,
        host: str = "0.0.0.0",
        allow_upload: bool = False,
        is_ipv6: bool = False,
        use_https: bool = False,
        certfile: Path | None = None,
    ):
        """Initialize SimpleHTTPServer.

        Args:
            port: Server port (default: 8000)
            directory: Directory to serve files from (default: current directory)
            host: IP address to bind to (default: '0.0.0.0')
            allow_upload: Enable file uploads (default: False)
            is_ipv6: Use IPv6 addressing (default: False)
            use_https: Enable HTTPS with SSL (default: False)
            certfile: Path to SSL certificate file (auto-generated if None)
        """
        self.port = port
        self.directory = Path(directory) if directory else Path.cwd()
        self.host = host
        self.allow_upload = allow_upload
        self.is_ipv6 = is_ipv6
        self.use_https = use_https
        self.certfile = certfile

        # Change to the specified directory
        if self.directory.exists() and self.directory.is_dir():
            os.chdir(self.directory)
            logger.info(f"Serving files from directory: {self.directory}")
        else:
            logger.warning(
                f"Directory {self.directory} does not exist, serving from current directory"
            )

        self.server = PHTTPServer(
            bind_ip=host,
            bind_port=port,
            is_ipv6=is_ipv6,
            use_https=use_https,
            certfile=certfile,
            requestHandler=SimpleHTTPHandler,
        )

    def start(self, daemon: bool = True) -> None:
        """Start the HTTP server in a background thread.

        Args:
            daemon: Run as daemon thread (default: True)

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
