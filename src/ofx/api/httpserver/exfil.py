"""Exfiltration HTTP server implementation."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from pathlib import Path

from ofx.api._compat import get_logger
from ofx.api.httpserver.server_base import BaseServerFacade

logger = get_logger()


def build_exfil_handler(upload_dir: Path) -> type[BaseHTTPRequestHandler]:
    """Create a request handler with injected upload directory."""

    class ExfilRequestHandler(BaseHTTPRequestHandler):
        """Custom HTTP request handler for ExfilServer.

        Handles file uploads via POST requests and serves uploaded files via GET.
        """

        def __init__(self, *args: object, **kwargs: object) -> None:
            self._upload_dir = upload_dir
            super().__init__(*args, **kwargs)

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
                        self._upload_dir.mkdir(parents=True, exist_ok=True)
                        file_path = self._upload_dir / filename

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
            if not self._upload_dir.exists():
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"No files uploaded yet.")
                return

            files = [f.name for f in self._upload_dir.iterdir() if f.is_file()]

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()

            if files:
                self.wfile.write(b"Uploaded files:\n")
                for filename in files:
                    self.wfile.write(f"- {filename}\n".encode())
            else:
                self.wfile.write(b"No files uploaded yet.")

        def _serve_file(self, filename: str) -> None:
            """Serve a specific uploaded file."""
            file_path = self._upload_dir / filename

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

    return ExfilRequestHandler


class ExfilServer(BaseServerFacade):
    """HTTP server for data exfiltration and file collection.

    Provides an HTTP server designed for collecting files and data from
    compromised systems. Supports file uploads via POST requests and
    file downloads via GET requests. Includes security measures to prevent
    directory traversal attacks.

    Example:
        >>> server = ExfilServer(host='0.0.0.0', port=8080, save_dir='/tmp/uploads')
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
        is_ipv6: bool = False,
        use_https: bool = False,
        certfile: Path | None = None,
    ):
        """Initialize ExfilServer.

        Args:
            port: Server port (default: 9000)
            save_dir: Directory to store uploaded files (default: ./exfil)
            auto_timestamp: Add timestamp to uploaded files (default: True)
            host: IP address to bind to (default: '0.0.0.0')
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

        self.upload_dir = Path(save_dir) if save_dir else Path("./exfil")
        self._auto_timestamp = auto_timestamp

        # Create upload directory if it doesn't exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Upload directory: {self.upload_dir}")

        handler = build_exfil_handler(self.upload_dir)
        self._server = self._create_server(handler)

    @property
    def save_dir(self) -> Path:
        """Get the save directory."""
        return self.upload_dir

    @property
    def auto_timestamp(self) -> bool:
        """Get the auto timestamp setting."""
        return self._auto_timestamp

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
