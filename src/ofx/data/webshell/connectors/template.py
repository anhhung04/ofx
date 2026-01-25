"""Built-in template-based webshell connector.

Uses the existing template system from ofx.data.webshell.templates
to generate webshells for PHP, JSP, ASP, and ASPX.
"""


from ofx.api.exploitation.webshell.shell.asp import AspShell
from ofx.api.exploitation.webshell.shell.aspx import AspxShell
from ofx.api.exploitation.webshell.shell.jsp import JspShell
from ofx.api.exploitation.webshell.shell.php import PhpShell
from ofx.data.webshell.connectors.base import WebshellConnector


class TemplateConnector(WebshellConnector):
    """Template-based webshell generator using built-in templates.

    This is the default connector that wraps the existing webshell
    generation system (PhpShell, JspShell, etc.).
    """

    def __init__(self):
        super().__init__(
            name="template",
            description="Built-in template-based webshell generator"
        )
        self._shells = {
            "php": PhpShell,
            "jsp": JspShell,
            "java": JspShell,
            "asp": AspShell,
            "aspx": AspxShell,
        }

    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: str | None = None,
        secret_value: str | None = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate webshell using built-in templates.

        Args:
            language: Target language ('php', 'jsp', 'asp', 'aspx')
            password: Password parameter name
            encoder: Encoding method
            secret_header: Optional HTTP header for authentication
            secret_value: Value for secret header
            inline: Remove whitespace for inline usage

        Returns:
            Generated webshell code

        Raises:
            ValueError: If language not supported
        """
        self.validate_params(language, password, encoder)

        language = language.lower()
        if language not in self._shells:
            raise ValueError(
                f"Language '{language}' not supported. "
                f"Supported: {', '.join(self._shells.keys())}"
            )

        shell_class = self._shells[language]
        shell = shell_class(
            password=password,
            encoder=encoder,
            secret_header=secret_header,
            secret_value=secret_value,
        )

        return shell.get_webshell(inline=inline)

    def get_supported_languages(self) -> list:
        """Get supported languages."""
        return list(self._shells.keys())

    def _check_availability(self) -> bool:
        """Template connector is always available."""
        return True
