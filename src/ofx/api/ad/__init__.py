"""Active Directory enumeration and attack command builders.

Submodules
----------
enum       -- BloodHound, LDAP queries, PowerView, share enumeration
execution  -- Pass-the-Hash, SMB exec, secretsdump, DCSync, spraying, ACL abuse
kerberos   -- Kerberoasting, AS-REP roasting, Pass-the-Ticket, Golden Ticket
"""

from __future__ import annotations

from .enum import (
    bloodhound_collection_command,
    enumerate_dc_command,
    enumerate_shares_command,
    ldap_query_command,
    powerview_command,
)
from .execution import (
    acl_abuse_commands,
    dcsync_command,
    pass_the_hash_command,
    secretsdump_command,
    smb_exec_command,
    spray_command,
)
from .kerberos import (
    asreproast_command,
    find_delegation_command,
    golden_ticket_command,
    kerberoast_command,
    pass_the_ticket_command,
)

__all__ = [
    # enum
    "bloodhound_collection_command",
    "ldap_query_command",
    "powerview_command",
    "enumerate_dc_command",
    "enumerate_shares_command",
    # execution
    "pass_the_hash_command",
    "smb_exec_command",
    "secretsdump_command",
    "dcsync_command",
    "spray_command",
    "acl_abuse_commands",
    # kerberos
    "kerberoast_command",
    "asreproast_command",
    "pass_the_ticket_command",
    "golden_ticket_command",
    "find_delegation_command",
]
