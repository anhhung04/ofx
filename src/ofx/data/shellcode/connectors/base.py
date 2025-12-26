"""Base connector interface for shellcode generation.

This module defines the abstract base class that all shellcode connectors must implement.
Connectors can generate shellcode using various methods:
- Local tools (msfvenom, pwntools, etc.)
- Remote machines (SSH, cloud APIs)
- Custom generators (user-defined)
"""

from abc import ABC, abstractmethod
from typing import Optional


class ShellcodeConnector(ABC):
    """Abstract base class for shellcode generation connectors.
    
    All shellcode connectors must inherit from this class and implement
    the generate() method. This ensures a consistent interface across
    all shellcode generation backends.
    
    Attributes:
        name: Unique identifier for this connector
        description: Human-readable description of what this connector does
        available: Whether this connector is currently usable (e.g., required tools installed)
    """
    
    def __init__(self, name: str, description: str = ""):
        """Initialize connector with metadata.
        
        Args:
            name: Unique connector identifier (e.g., 'msfvenom', 'remote-aws', 'custom')
            description: Human-readable description
        """
        self.name = name
        self.description = description
        self._available: Optional[bool] = None
    
    @abstractmethod
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
        custom_params: Optional[dict] = None,
    ) -> bytes:
        """Generate shellcode with specified parameters.
        
        This method must be implemented by all connectors. It should return
        raw shellcode bytes ready for use or further processing.
        
        Args:
            os_target: Target operating system ('linux', 'windows', 'osx', etc.)
            arch: Target architecture ('x86', 'x64', 'arm', 'aarch64', etc.)
            shell_type: Type of shellcode ('reverse', 'bind', 'exec', etc.)
            ip: IP address for connection (for reverse/bind shells)
            port: Port number for connection
            bad_chars: List of bad characters to avoid (e.g., ["\\x00", "\\x0a"])
            encoder: Optional encoder name (connector-specific)
            iterations: Number of encoding iterations
            custom_params: Additional connector-specific parameters
        
        Returns:
            Raw shellcode bytes
        
        Raises:
            NotImplementedError: Must be implemented by subclass
            RuntimeError: If shellcode generation fails
            ValueError: If parameters are invalid
        
        Example:
            >>> connector = MyConnector()
            >>> shellcode = connector.generate(
            ...     os_target='linux',
            ...     arch='x64',
            ...     shell_type='reverse',
            ...     ip='192.168.1.100',
            ...     port=4444
            ... )
            >>> len(shellcode)
            103
        """
        raise NotImplementedError("Connectors must implement generate() method")
    
    def is_available(self) -> bool:
        """Check if this connector is currently available.
        
        Connectors should override this to check for required dependencies,
        network connectivity, API keys, etc. The result is cached to avoid
        repeated expensive checks.
        
        Returns:
            True if connector can be used, False otherwise
        
        Example:
            >>> connector = MsfvenomConnector()
            >>> if connector.is_available():
            ...     shellcode = connector.generate(...)
        """
        if self._available is None:
            self._available = self._check_availability()
        return self._available
    
    def _check_availability(self) -> bool:
        """Internal method to check availability.
        
        Subclasses should override this instead of is_available() to implement
        their availability check logic.
        
        Returns:
            True if available, False otherwise
        """
        return True
    
    def get_supported_platforms(self) -> list[tuple[str, str, str]]:
        """Get list of supported platform combinations.
        
        Returns:
            List of (os_target, arch, shell_type) tuples
        
        Example:
            >>> connector = MsfvenomConnector()
            >>> platforms = connector.get_supported_platforms()
            >>> ('linux', 'x64', 'reverse') in platforms
            True
        """
        return []
    
    def validate_parameters(
        self,
        os_target: str,
        arch: str,
        shell_type: str,
        ip: str,
        port: int,
    ) -> None:
        """Validate parameters before generation.
        
        Subclasses can override this to add parameter validation.
        
        Args:
            os_target: Target OS
            arch: Target architecture
            shell_type: Shellcode type
            ip: IP address
            port: Port number
        
        Raises:
            ValueError: If parameters are invalid
        """
        if not 0 <= port <= 65535:
            raise ValueError(f"Invalid port {port} (must be 0-65535)")
    
    def __repr__(self) -> str:
        """String representation of connector."""
        status = "available" if self.is_available() else "unavailable"
        return f"<{self.__class__.__name__}(name='{self.name}', status='{status}')>"
