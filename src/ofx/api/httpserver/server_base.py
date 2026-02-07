"""Base server facade for HTTP servers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ofx.api.httpserver.base import PHTTPServer


class BaseServerFacade(ABC):
    """Abstract base class for HTTP server facades.

    Provides common functionality for all HTTP server types including
    lifecycle management (start, stop, pause, resume) and property access.

    Subclasses should:
    1. Call super().__init__() with appropriate parameters
    2. Create a custom request handler class
    3. Initialize self._server in their __init__

    Example:
        >>> class MyServer(BaseServerFacade):
        ...     def __init__(self, host="0.0.0.0", port=8080):
        ...         super().__init__(host=host, port=port)
        ...         self._server = self._create_server(MyRequestHandler)
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        is_ipv6: bool = False,
        use_https: bool = False,
        certfile: Path | None = None,
    ):
        """Initialize base server facade.

        Args:
            host: IP address to bind to (default: '0.0.0.0')
            port: Port to bind to (default: 8080)
            is_ipv6: Use IPv6 addressing (default: False)
            use_https: Enable HTTPS with SSL (default: False)
            certfile: Path to SSL certificate file (auto-generated if None)
        """
        self.host = host
        self.port = port
        self.is_ipv6 = is_ipv6
        self.use_https = use_https
        self.certfile = certfile
        self._server: PHTTPServer | None = None

    def _create_server(self, handler: type[BaseHTTPRequestHandler]) -> PHTTPServer:
        """Create a PHTTPServer instance with the specified handler.

        Args:
            handler: Request handler class to use

        Returns:
            Configured PHTTPServer instance
        """
        from ofx.api.httpserver.base import PHTTPServer

        return PHTTPServer(
            bind_ip=self.host,
            bind_port=self.port,
            is_ipv6=self.is_ipv6,
            use_https=self.use_https,
            certfile=self.certfile,
            requestHandler=handler,
        )

    def start(self, daemon: bool = True) -> None:
        """Start the HTTP server in a background thread.

        Args:
            daemon: Run as daemon thread that exits when main program exits (default: True)
        """
        if self._server:
            self._server.start(daemon=daemon)

    def stop(self) -> None:
        """Stop the HTTP server and release all resources."""
        if self._server:
            self._server.stop()

    def pause(self) -> None:
        """Pause the HTTP server without terminating the thread."""
        if self._server:
            self._server.pause()

    def resume(self) -> None:
        """Resume a paused HTTP server to continue handling requests."""
        if self._server:
            self._server.resume()

    @property
    def url(self) -> str:
        """Get the server URL.

        Returns:
            Server URL including protocol, IP, and port
        """
        return self._server.url if self._server else ""

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running.

        Returns:
            True if server is running, False otherwise
        """
        return self._server.server_started if self._server else False
