"""Shell escaping utilities shared across cloud and runner modules."""

from __future__ import annotations

def bash_dquote_escape(value: str) -> str:
    """Escape a string for safe embedding inside bash double-quoted contexts.

    Escapes backslashes, double-quotes, backticks, and ``$`` so the value is
    interpreted literally by the shell, preventing command substitution and
    variable expansion.

    Example::

        cmd = f'VAR="{bash_dquote_escape(untrusted)}"'
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
