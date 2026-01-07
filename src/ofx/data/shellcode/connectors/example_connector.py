"""Example custom shellcode connector.

This is a template showing how to create your own shellcode connector.
Place custom connector files in this directory and they will be auto-discovered.

To create a custom connector:
1. Create a new Python file in this directory (e.g., my_connector.py)
2. Import ShellcodeConnector from ofx.api.shellcode.connectors
3. Create a class that inherits from ShellcodeConnector
4. Implement the generate() method
5. Optionally override _check_availability() and get_supported_platforms()

The connector will be automatically loaded when the shellcode module is used.
"""

import logging
import struct

from ofx.data.shellcode.connectors.base import ShellcodeConnector

logger = logging.getLogger(__name__)


class ExampleConnector(ShellcodeConnector):
    """Example custom shellcode connector.

    This connector demonstrates:
    - Basic shellcode generation
    - Parameter validation
    - Availability checking
    - Platform support declaration

    You can customize this for:
    - Calling external tools/scripts
    - Generating custom payloads
    - Integrating with proprietary systems
    - Wrapping existing shellcode generators
    """

    def __init__(self):
        """Initialize the example connector."""
        super().__init__(
            name="example",
            description="Example custom shellcode generator (demonstration only)"
        )

    def _check_availability(self) -> bool:
        """Check if this connector is available.

        Override this to check for:
        - Required tools installed (shutil.which('tool_name'))
        - Configuration files exist
        - Network connectivity to remote services
        - API keys/credentials configured

        Returns:
            True if connector can be used
        """
        return True

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
        """Generate shellcode.

        This is a minimal example that creates a simple NOP sled with
        IP and port embedded. Real connectors would:
        - Call external tools (msfvenom, custom scripts)
        - Generate proper shellcode
        - Handle encoding and bad character avoidance
        - Support multiple platforms

        Args:
            os_target: Target OS ('linux', 'windows', 'osx')
            arch: Architecture ('x86', 'x64', 'arm')
            shell_type: Shellcode type ('reverse', 'bind', 'exec')
            ip: IP address for connection
            port: Port number
            bad_chars: Characters to avoid
            encoder: Encoder name
            iterations: Encoding iterations
            custom_params: Additional parameters

        Returns:
            Raw shellcode bytes

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If generation fails
        """
        self.validate_parameters(os_target, arch, shell_type, ip, port)

        logger.info(
            f"Generating example shellcode: {os_target}/{arch}/{shell_type} "
            f"{ip}:{port}"
        )

        nop_sled = b'\x90' * 10

        ip_bytes = bytes(map(int, ip.split('.')))

        port_bytes = struct.pack('>H', port)

        marker = b'\xCC' * 4

        shellcode = nop_sled + ip_bytes + port_bytes + marker

        if bad_chars:
            for bad_char in bad_chars:
                if isinstance(bad_char, str):
                    bad_byte = bytes.fromhex(bad_char.replace('\\x', ''))
                else:
                    bad_byte = bad_char.encode() if isinstance(bad_char, str) else bad_char

                if bad_byte in shellcode:
                    logger.warning(
                        f"Bad character {bad_char} found in shellcode! "
                        "Real connectors should handle this properly."
                    )

        if encoder:
            logger.info(f"Encoding requested: {encoder} (not implemented in example)")

        logger.info(f"Generated example shellcode: {len(shellcode)} bytes")

        return shellcode

    def get_supported_platforms(self) -> list[tuple[str, str, str]]:
        """Get list of supported platforms.

        Returns:
            List of (os_target, arch, shell_type) tuples
        """
        return [
            ('linux', 'x64', 'reverse'),
            ('linux', 'x86', 'reverse'),
            ('windows', 'x64', 'reverse'),
            ('windows', 'x86', 'reverse'),
        ]


class AnotherExampleConnector(ShellcodeConnector):
    """Another example showing how multiple connectors can coexist."""

    def __init__(self):
        super().__init__(
            name="another-example",
            description="Another example connector"
        )

    def generate(self, *args, **kwargs) -> bytes:
        """Generate shellcode."""
        return b'\x90' * 100

    def get_supported_platforms(self) -> list[tuple[str, str, str]]:
        return [('linux', 'x64', 'bind')]
