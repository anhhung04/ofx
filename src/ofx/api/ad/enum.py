"""Active Directory enumeration command builders."""

from __future__ import annotations

__all__ = [
    "bloodhound_collection_command",
    "ldap_query_command",
    "powerview_command",
    "enumerate_dc_command",
    "enumerate_shares_command",
]


def bloodhound_collection_command(
    domain: str,
    username: str,
    password: str,
    dc: str,
    *,
    collection_method: str = "All",
    stealth: bool = False,
    zip_filename: str = "loot.zip",
) -> str:
    """Build a SharpHound (BloodHound CE) ingestor command.

    Args:
        collection_method: ``All``, ``DCOnly``, ``Default``, ``Session``, etc.
        stealth: Use ``DCOnly`` to reduce wire noise.
    """
    method = "DCOnly" if stealth else collection_method
    return (
        f"SharpHound.exe -c {method} -d {domain} "
        f"--ldapusername {username} --ldappassword '{password}' "
        f"--domaincontroller {dc} --zipfilename {zip_filename}"
    )


def ldap_query_command(
    dc_ip: str,
    domain: str,
    username: str,
    password: str,
    *,
    query: str = "(objectClass=user)",
    attributes: list[str] | None = None,
    base_dn: str = "",
) -> str:
    """Build an ldapsearch command for AD enumeration."""
    attrs = (
        " ".join(attributes)
        if attributes
        else "sAMAccountName memberOf userPrincipalName description"
    )
    dn = base_dn or "DC=" + ",DC=".join(domain.split("."))
    return (
        f"ldapsearch -x -H ldap://{dc_ip} -D '{username}@{domain}' -w '{password}' "
        f"-b '{dn}' '{query}' {attrs}"
    )


def powerview_command(
    module: str,
    *,
    domain: str = "",
    identity: str = "",
    extra_args: str = "",
) -> str:
    """Return a PowerView invocation snippet.

    Example modules: ``Get-DomainUser``, ``Get-DomainGroup``,
    ``Find-LocalAdminAccess``, ``Get-ObjectAcl``, ``Find-DomainShare``,
    ``Get-DomainTrust``, ``Invoke-ACLScanner``.
    """
    parts = ["Import-Module PowerView.ps1;", module]
    if domain:
        parts.append(f"-Domain {domain}")
    if identity:
        parts.append(f"-Identity '{identity}'")
    if extra_args:
        parts.append(extra_args)
    return " ".join(parts)


def enumerate_dc_command(domain: str) -> list[str]:
    """Return commands to locate domain controllers for *domain*."""
    return [
        f"nslookup -type=SRV _ldap._tcp.dc._msdcs.{domain}",
        f"dig +short SRV _ldap._tcp.dc._msdcs.{domain}",
        f"nltest /dclist:{domain} 2>/dev/null || true",
    ]


def enumerate_shares_command(
    target: str,
    username: str,
    password: str,
    domain: str = ".",
) -> str:
    """Build a netexec command to enumerate SMB shares and check access."""
    return f"netexec smb {target} -u {username} -p '{password}' -d {domain} --shares"
