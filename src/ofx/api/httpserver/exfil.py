"""Exfiltration HTTP server implementation."""

from __future__ import annotations

import logging
import os
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from ofx.api.httpserver.base import PHTTPServer
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class ExfilRequestHandler(BaseHTTPRequestHandler):
    """Custom HTTP request handler for ExfilServer.

    Handles file uploads via POST requests and serves uploaded files via GET.
    """

    def log_message(self, format: str, *args: object) -> None:
        logger.info(
            f"{self.address_string()} - - [{self.log_date_time_string()}] {format % args}\n"
        )

    def do_GET(self) -> None:
        """Handle GET requests for listing or downloading uploaded files.

        Supports:
        - / : List all uploaded files
        - /<filename> : Download specific file
        """
        if self.path == "/":
            self._list_files()
        else:
            filename = self.path.lstrip("/")
            self._serve_file(filename)

    def do_POST(self) -> None:
        """Handle POST requests for file uploads.

        Expects multipart/form-data with file uploads.
        Files are saved to the server's upload directory.
        """
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self.send_error(400, "Expected multipart/form-data")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_error(400, "No content provided")
            return

        body = self.rfile.read(content_length)
        boundary = self._get_boundary(content_type)

        if not boundary:
            self.send_error(400, "Invalid multipart data")
            return

        files_saved = self._parse_multipart(body, boundary)

        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(f"Files uploaded: {', '.join(files_saved)}".encode())

    def _get_boundary(self, content_type: str) -> str | None:
        """Extract boundary from Content-Type header."""
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part.split("=", 1)[1].strip()
                if boundary.startswith('"') and boundary.endswith('"'):
                    boundary = boundary[1:-1]
                return boundary
        return None

    def _parse_multipart(self, body: bytes, boundary: str) -> list[str]:
        """Parse multipart form data and save files."""
        boundary_bytes = f"--{boundary}".encode()
        parts = body.split(boundary_bytes)

        files_saved = []
        upload_dir = getattr(
            self.server, "upload_dir", Path(tempfile.gettempdir()) / "ofx_exfil"
        )

        for part in parts:
            if not part or part == b"--\r\n" or part == b"--":
                continue

            headers_end = part.find(b"\r\n\r\n")
            if headers_end == -1:
                continue

            headers = part[:headers_end].decode("utf-8", errors="ignore")
            content = part[headers_end + 4 :]

            # Check for Content-Disposition header
            if "Content-Disposition: form-data;" in headers:
                filename = None
                for line in headers.split("\r\n"):
                    if "filename=" in line:
                        filename_part = line.split("filename=")[1].strip()
                        if filename_part.startswith('"') and filename_part.endswith(
                            '"'
                        ):
                            filename = filename_part[1:-1]
                        else:
                            filename = filename_part
                        break

                if filename:
                    upload_dir.mkdir(parents=True, exist_ok=True)
                    file_path = upload_dir / filename

                    # Prevent directory traversal
                    if ".." in filename or "/" in filename or "\\" in filename:
                        logger.warning(
                            f"Blocked potential directory traversal: {filename}"
                        )
                        continue

                    try:
                        with open(file_path, "wb") as f:
                            f.write(content.rstrip(b"\r\n"))
                        files_saved.append(filename)
                        logger.info(
                            f"File uploaded: {filename} from {self.client_address[0]}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to save file {filename}: {e}")

        return files_saved

    def _list_files(self) -> None:
        """List all uploaded files."""
        upload_dir = getattr(
            self.server, "upload_dir", Path(tempfile.gettempdir()) / "ofx_exfil"
        )

        if not upload_dir.exists():
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"No files uploaded yet.")
            return

        files = [f.name for f in upload_dir.iterdir() if f.is_file()]

        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

        if files:
            self.wfile.write("Uploaded files:\n".encode())
            for filename in files:
                self.wfile.write(f"- {filename}\n".encode())
        else:
            self.wfile.write(b"No files uploaded yet.")

    def _serve_file(self, filename: str) -> None:
        """Serve a specific uploaded file."""
        upload_dir = getattr(
            self.server, "upload_dir", Path(tempfile.gettempdir()) / "ofx_exfil"
        )
        file_path = upload_dir / filename

        # Prevent directory traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            self.send_error(403, "Access denied")
            return

        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File not found")
            return

        try:
            self.send_response(200)
            self.send_header("Content-type", "application/octet-stream")
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
            self.end_headers()

            with open(file_path, "rb") as f:
                self.wfile.write(f.read())

            logger.info(f"File served: {filename} to {self.client_address[0]}")
        except Exception as e:
            logger.error(f"Failed to serve file {filename}: {e}")
            self.send_error(500, "Internal server error")


class ExfilServer:
    """HTTP server for data exfiltration and file collection.

    Provides an HTTP server designed for collecting files and data from
    compromised systems. Supports file uploads via POST requests and
    file downloads via GET requests. Includes security measures to prevent
    directory traversal attacks.

    Example:
        >>> server = ExfilServer(bind_ip='0.0.0.0', bind_port=8080, upload_dir='/tmp/uploads')
        >>> server.start()
        >>> # Server is now accepting file uploads at http://0.0.0.0:8080
        >>> # Files can be listed at http://0.0.0.0:8080/ and downloaded individually
        >>> server.stop()
    """

    def __init__(
        self,
        port: int = 9000,
        save_dir: str | Path | None = None,
        auto_timestamp: bool = True,
        host: str = "0.0.0.0",
    ):
        """Initialize ExfilServer.

        Args:
            bind_ip: IP address to bind to (default: '0.0.0.0')
            bind_port: Port to bind to (default: 6666)
            upload_dir: Directory to store uploaded files (default: temp directory)
            is_ipv6: Use IPv6 addressing (default: False)
            use_https: Enable HTTPS with SSL (default: False)
            certfile: Path to SSL certificate file (auto-generated if None)
        """
        self.bind_ip = host
        self.bind_port = port
        self.upload_dir = Path(save_dir) if save_dir else Path("./exfil")
        self._auto_timestamp = auto_timestamp
        self.is_ipv6 = False
        self.use_https = False
        self.certfile = None

        # Create upload directory if it doesn't exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Upload directory: {self.upload_dir}")

        self.server = PHTTPServer(
            bind_ip=host,
            bind_port=port,
            is_ipv6=False,
            use_https=False,
            certfile=None,
            requestHandler=ExfilRequestHandler,
        )

        # Store upload directory in server instance for handler access
        self.server.upload_dir = self.upload_dir

    @property
    def port(self) -> int:
        """Get the server port."""
        return self.bind_port

    @property
    def host(self) -> str:
        """Get the server host."""
        return self.bind_ip

    @property
    def save_dir(self) -> Path:
        """Get the save directory."""
        return self.upload_dir

    @property
    def auto_timestamp(self) -> bool:
        """Get the auto timestamp setting."""
        return self._auto_timestamp

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

    def list_files(self) -> list[str]:
        """List all uploaded files.

        Returns:
            List of uploaded filenames
        """
        if not self.upload_dir.exists():
            return []

        return [f.name for f in self.upload_dir.iterdir() if f.is_file()]

    def get_file_path(self, filename: str) -> Path | None:
        """Get the full path to an uploaded file.

        Args:
            filename: Name of the uploaded file

        Returns:
            Full path to the file, or None if file doesn't exist
        """
        file_path = self.upload_dir / filename
        if file_path.exists() and file_path.is_file():
            return file_path
        return None
