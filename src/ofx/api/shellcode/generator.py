"""
Shellcode generator with custom template support.
"""

import ipaddress
import logging
from typing import Callable, Optional

from ofx.settings import settings

from .templates import SHELLCODE_TEMPLATES

logger = logging.getLogger(settings.app_branding)


class ShellGenerator:
    """Shellcode generation with custom template registry"""

    # Class-level template registry for custom shellcode templates
    _custom_templates: dict[str, Callable[[str, int], bytes] | bytes] = {}

    def __init__(self, os_target: str, os_target_arch: str):
        """
        Initialize shellcode generator.

        Args:
            os_target: Target OS (linux, windows)
            os_target_arch: Target architecture (x86, x64)
        """
        self.OS_TARGET = os_target.upper()
        self.OS_TARGET_ARCH = os_target_arch.upper()

    @classmethod
    def register_template(
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
            >>> def my_custom_shell(ip: str, port: int) -> bytes:
            ...     ip_bytes = bytes(map(int, ip.split(".")))
            ...     port_bytes = struct.pack(">H", port)
            ...     return b"\\x90" * 10 + ip_bytes + port_bytes
            >>>
            >>> ShellGenerator.register_template("linux", "x64", "custom", my_custom_shell)
        """
        key = f"{os_target.upper()}_{os_target_arch.upper()}_{shellcode_type}"
        cls._custom_templates[key] = template
        logger.info(f"Registered custom shellcode template: {key}")

    @classmethod
    def unregister_template(
        cls, os_target: str, os_target_arch: str, shellcode_type: str
    ) -> None:
        """
        Unregister a custom shellcode template.

        Args:
            os_target: Target OS
            os_target_arch: Target architecture
            shellcode_type: Type of shellcode
        """
        key = f"{os_target.upper()}_{os_target_arch.upper()}_{shellcode_type}"
        if key in cls._custom_templates:
            del cls._custom_templates[key]
            logger.info(f"Unregistered custom template: {key}")

    @classmethod
    def clear_templates(cls) -> None:
        """Clear all custom templates"""
        cls._custom_templates.clear()
        logger.info("Cleared all custom shellcode templates")

    @classmethod
    def list_templates(cls) -> list[str]:
        """
        List all registered custom templates.

        Returns:
            List of template keys (e.g., ["LINUX_X64_custom", "WINDOWS_X86_reverse"])
        """
        return list(cls._custom_templates.keys())

    def _get_custom_template(
        self, shellcode_type: str
    ) -> Optional[Callable[[str, int], bytes] | bytes]:
        """
        Get custom template if registered.

        Args:
            shellcode_type: Type of shellcode

        Returns:
            Template function or raw bytes, or None if not found
        """
        key = f"{self.OS_TARGET}_{self.OS_TARGET_ARCH}_{shellcode_type}"
        return self._custom_templates.get(key)

    def _validate_settings(self, addr: str, port: int) -> None:
        """
        Validate IP address and port number.

        Args:
            addr: IP address or hostname
            port: Port number

        Raises:
            ValueError: If IP or port is invalid
        """
        from socket import gethostbyname

        try:
            addr = gethostbyname(addr)
            ipaddress.ip_address(addr)
        except (ValueError, OSError) as e:
            raise ValueError(f"IP address {addr} is not valid: {e}")

        if not 0 <= port <= 65535:
            raise ValueError(f"PORT {port} is not valid (must be 0-65535)")

    def get_shellcode(
        self,
        shellcode_type: str,
        connectback_ip: str = "127.0.0.1",
        connectback_port: int = 5555,
        make_exe: int = 0,
        debug: int = 0,
        filename: str = "",
        dll_inj_funcs: list[str] | None = None,
        shell_args: dict | None = None,
        use_precompiled: bool = True,
    ) -> tuple[bytes, str]:
        """
        Generate shellcode.

        Args:
            shellcode_type: Type of shellcode (reverse, bind, custom)
            connectback_ip: IP address for connection
            connectback_port: Port for connection
            make_exe: Whether to create executable (1) or not (0)
            debug: Enable debug output (1) or not (0)
            filename: Output filename for executable
            dll_inj_funcs: DLL injection functions (Windows)
            shell_args: Additional shell arguments
            use_precompiled: Use precompiled shellcode if available

        Returns:
            Tuple of (shellcode_bytes, executable_filepath)
        """
        dll_inj_funcs = dll_inj_funcs or []
        shell_args = shell_args or {}

        self._validate_settings(connectback_ip, connectback_port)

        shellcode = self._generate_shellcode(
            shellcode_type, connectback_ip, connectback_port
        )

        filepath = ""

        if debug:
            logger.debug(f"Shellcode generated: length={len(shellcode)} bytes")
            logger.debug(f"Hex: {shellcode.hex()}")
            logger.debug(b"".join(b"\\x%02x" % x for x in shellcode).decode("ascii"))

        if make_exe:
            from .exe import ShellcodeToExe

            exe_gen = ShellcodeToExe(
                shellcode,
                self.OS_TARGET,
                self.OS_TARGET_ARCH,
                filename=filename,
                dll_inj_funcs=dll_inj_funcs,
            )
            filepath = exe_gen.create_executable()
            if debug:
                logger.debug(f"Executable created: {filepath}")

        return shellcode, filepath

    def _generate_shellcode(self, shellcode_type: str, ip: str, port: int) -> bytes:
        """
        Generate shellcode from templates.

        Args:
            shellcode_type: Type of shellcode
            ip: IP address
            port: Port number

        Returns:
            Raw shellcode bytes
        """
        # Check for custom template first
        custom_template = self._get_custom_template(shellcode_type)
        if custom_template is not None:
            if callable(custom_template):
                logger.info(
                    f"Using custom template: {self.OS_TARGET}_{self.OS_TARGET_ARCH}_{shellcode_type}"
                )
                return custom_template(ip, port)
            else:
                # Raw bytes template
                logger.info("Using custom raw bytes template")
                return custom_template

        # Fall back to built-in templates
        try:
            template_func = SHELLCODE_TEMPLATES[self.OS_TARGET][self.OS_TARGET_ARCH][
                shellcode_type
            ]
            logger.debug(
                f"Using built-in template: {self.OS_TARGET}/{self.OS_TARGET_ARCH}/{shellcode_type}"
            )
            return template_func(ip, port)
        except KeyError:
            raise ValueError(
                f"Unsupported OS/ARCH/TYPE combination: {self.OS_TARGET}/{self.OS_TARGET_ARCH}/{shellcode_type}. "
                f"Available: {self._list_available_templates()}"
            )

    def _list_available_templates(self) -> str:
        """List all available built-in templates"""
        templates = []
        for os in SHELLCODE_TEMPLATES:
            for arch in SHELLCODE_TEMPLATES[os]:
                for stype in SHELLCODE_TEMPLATES[os][arch]:
                    templates.append(f"{os}/{arch}/{stype}")
        return ", ".join(templates)
