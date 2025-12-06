"""
JSP webshell generation for AntSword protocol compatibility.
"""

from typing import Optional

from ofx.api.webshell.base import WebShell
from ofx.data.webshell.templates import JSP_TEMPLATES


class JspShell(WebShell):
    """JSP AntSword-compatible webshell generation"""

    def __init__(
        self,
        password: str = "pass",
        encoder: str = "default",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
    ):
        """
        Initialize JSP webshell generator.

        Args:
            password: Password parameter name (default: 'pass')
            encoder: Encoding type - 'default', 'base64', 'script_engine', 'auth' (default: 'default')
            secret_header: Optional HTTP header name for authentication
            secret_value: Optional HTTP header value for authentication
        """
        super().__init__(password, encoder, secret_header, secret_value, "", "")

    def get_webshell(self, inline: bool = False) -> str:
        """
        Generate AntSword-compatible JSP webshell.

        Args:
            inline: Remove whitespace for inline usage

        Returns:
            JSP webshell code
        """
        # Check for custom template
        custom = self._get_custom_template("jsp")
        if custom:
            return self.apply_template(custom)

        # Use authentication template if secret header is configured
        if self.secret_header and self.secret_value and self.encoder == "default":
            template = JSP_TEMPLATES["auth"]
            code = self.apply_template(template)
        # Use built-in template based on encoder
        elif self.encoder in JSP_TEMPLATES:
            template = JSP_TEMPLATES[self.encoder]
            code = self.apply_template(template)
        else:
            # Default fallback
            template = JSP_TEMPLATES["default"]
            code = self.apply_template(template)

        if inline:
            code = self.make_inline(code)

        return code

    def get_script_engine_shell(self) -> str:
        """Generate ScriptEngine-based JSP webshell"""
        template = JSP_TEMPLATES["script_engine"]
        code = self.apply_template(template)
        return code
