"""Tests for individual tool parsers, parse_line, streaming detection, and output edge cases."""

import json

from ofx.tasks import (
    TaskRegistry,
    Vulnerability,
)
from ofx.tasks.output_types import (
    Tag,
    UserAccount,
)

class TestNetexecParser:
    def test_netexec_metadata(self):
        task = TaskRegistry.create("netexec")
        assert task.name == "netexec"
        assert task.cmd == "nxc"
        assert task.category == "ad/enum"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_netexec_parse_output(self):
        stdout = "\n".join(
            [
                "SMB  10.0.0.1  445  DC01  [+] CORP\\admin:P@ssw0rd (Pwn3d!)",
                "SMB  10.0.0.1  445  DC01  [+] CORP\\user1:password123",
                "SMB  10.0.0.1  445  DC01  [-] CORP\\baduser:wrong STATUS_LOGON_FAILURE",
                "SMB  10.0.0.1  445  DC01  [*] Windows 10.0 Build 17763 x64",
            ]
        )
        task = TaskRegistry.create("netexec")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag, UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(users) == 2
        assert users[0].username == "admin"
        assert users[0].domain == "CORP"
        assert users[0].password == "P@ssw0rd"
        assert users[0].privilege_level == "admin"
        assert users[1].username == "user1"
        assert users[1].privilege_level == ""
        assert len(tags) == 1
        assert tags[0].name == "info"

    def test_netexec_parse_hash_login(self):
        stdout = "SMB  10.0.0.1  445  DC01  [+] CORP\\admin:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0"
        task = TaskRegistry.create("netexec")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        assert len(users) == 1
        assert (
            users[0].hash
            == "aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0"
        )
        assert users[0].password == ""

    def test_netexec_parse_user_enum(self):
        stdout = "SMB 445 DC01 jsmith rid: 1105"
        task = TaskRegistry.create("netexec")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        assert len(users) == 1
        assert users[0].username == "jsmith"
        assert "RID:1105" in users[0].comment

    def test_netexec_parse_share_enum(self):
        stdout = "SMB 445 DC01 ADMIN$ READ"
        task = TaskRegistry.create("netexec")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import Tag

        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 1
        assert tags[0].name == "share"
        assert tags[0].value == "ADMIN$"

    def test_netexec_parse_empty(self):
        task = TaskRegistry.create("netexec")
        assert task.parse_output("", "") == []

    def test_netexec_build_command(self):
        task = TaskRegistry.create("netexec")
        cmd, _ = task.build_command(
            "10.0.0.1",
            protocol="smb",
            username="admin",
            password="pass",
            shares=True,
        )
        assert "nxc smb 10.0.0.1" in cmd
        assert "-u admin" in cmd
        assert "-p pass" in cmd
        assert "--shares" in cmd

class TestKerbruteParser:
    def test_kerbrute_metadata(self):
        task = TaskRegistry.create("kerbrute")
        assert task.name == "kerbrute"
        assert task.cmd == "kerbrute"
        assert task.category == "ad/brute"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_kerbrute_parse_output(self):
        stdout = "\n".join(
            [
                "2024/01/15 10:00:00 >  [+] VALID USERNAME:	 admin@corp.local",
                "2024/01/15 10:00:01 >  [+] VALID USERNAME:	 jsmith@corp.local",
                "2024/01/15 10:00:02 >  [+] VALID LOGIN:	 admin@corp.local:Password1",
                "2024/01/15 10:00:03 >  [-] INVALID USERNAME:  fakeuser@corp.local",
            ]
        )
        task = TaskRegistry.create("kerbrute")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        assert len(users) == 3
        assert users[0].username == "admin"
        assert users[0].domain == "corp.local"
        assert users[0].password == ""
        assert users[1].username == "jsmith"
        assert users[1].domain == "corp.local"
        assert users[1].password == ""
        assert users[2].username == "admin"
        assert users[2].password == "Password1"

    def test_kerbrute_parse_empty(self):
        task = TaskRegistry.create("kerbrute")
        assert task.parse_output("", "") == []

    def test_kerbrute_build_command(self):
        task = TaskRegistry.create("kerbrute")
        cmd, _ = task.build_command(
            "/tmp/users.txt",
            mode="userenum",
            dc="10.0.0.1",
            domain="corp.local",
            threads=20,
        )
        assert "kerbrute userenum" in cmd
        assert "--dc 10.0.0.1" in cmd
        assert "-d corp.local" in cmd
        assert "-t 20" in cmd
        assert "/tmp/users.txt" in cmd

class TestEnum4linuxParser:
    def test_enum4linux_metadata(self):
        task = TaskRegistry.create("enum4linux")
        assert task.name == "enum4linux"
        assert task.cmd == "enum4linux-ng"
        assert task.category == "ad/enum"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_enum4linux_parse_output(self):
        data = {
            "users": {
                "500": {"username": "Administrator", "domain": "CORP"},
                "1001": {"username": "jsmith", "domain": "CORP"},
            },
            "shares": [
                {"name": "ADMIN$"},
                {"name": "IPC$"},
            ],
            "groups": [
                {"groupname": "Domain Admins"},
                {"groupname": "Domain Users"},
            ],
            "os_info": {"OS": "Windows 10.0 Build 17763"},
        }
        task = TaskRegistry.create("enum4linux")
        results = task.parse_output(json.dumps(data), "")
        from ofx.tasks.output_types import Tag, UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(users) == 2
        assert users[0].username == "Administrator"
        assert users[0].domain == "CORP"
        shares = [t for t in tags if t.name == "share"]
        groups = [t for t in tags if t.name == "group"]
        os_tags = [t for t in tags if t.name == "os"]
        assert len(shares) == 2
        assert len(groups) == 2
        assert len(os_tags) == 1
        assert os_tags[0].value == "Windows 10.0 Build 17763"

    def test_enum4linux_parse_empty(self):
        task = TaskRegistry.create("enum4linux")
        assert task.parse_output("", "") == []

    def test_enum4linux_parse_invalid_json(self):
        task = TaskRegistry.create("enum4linux")
        assert task.parse_output("not json", "") == []

    def test_enum4linux_build_command(self):
        task = TaskRegistry.create("enum4linux")
        cmd, out_file = task.build_command(
            "10.0.0.1", username="admin", password="pass"
        )
        assert "enum4linux-ng" in cmd
        assert "-A" in cmd
        assert "-u admin" in cmd
        assert "-p pass" in cmd
        assert "-oJ" in cmd
        assert "10.0.0.1" in cmd
        assert out_file is not None
        if out_file and out_file.exists():
            out_file.unlink()

    def test_enum4linux_build_command_no_default_A(self):
        task = TaskRegistry.create("enum4linux")
        cmd, out_file = task.build_command("10.0.0.1", users=True)
        assert "-A" not in cmd
        assert "-U" in cmd
        if out_file and out_file.exists():
            out_file.unlink()

class TestSecretsdumpParser:
    def test_build_command(self):
        task = TaskRegistry.create("secretsdump")
        cmd, _ = task.build_command(
            "10.0.0.1",
            username="admin",
            password="pass",
            domain="CORP",
            just_dc_ntlm=True,
        )
        assert "impacket-secretsdump" in cmd
        assert "-just-dc-ntlm" in cmd
        assert "CORP/admin:pass@10.0.0.1" in cmd

    def test_build_command_with_hashes(self):
        task = TaskRegistry.create("secretsdump")
        cmd, _ = task.build_command(
            "10.0.0.1",
            username="admin",
            domain="CORP",
            hash="aad3b435b51404ee:31d6cfe0d16ae931",
        )
        assert "-hashes aad3b435b51404ee:31d6cfe0d16ae931" in cmd
        assert "CORP/admin@10.0.0.1" in cmd

    def test_parse_ntds_output(self):
        task = TaskRegistry.create("secretsdump")
        stdout = (
            "Impacket v0.11.0 - Copyright ...\n"
            "[*] Dumping NTDS.dit\n"
            "Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::\n"
            "Guest:501:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::\n"
            "CORP\\svc_sql:1103:aad3b435b51404eeaad3b435b51404ee:fc525c9683e8fe067095ba2ddc971889:::\n"
            "$MACHINE.ACC:aad3b435b51404eeaad3b435b51404ee:deadbeefdeadbeefdeadbeefdeadbeef:::\n"
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, UserAccount) for r in results)
        assert results[0].username == "Administrator"
        assert results[0].comment == "RID:500"
        assert results[2].username == "svc_sql"
        assert results[2].domain == "CORP"

    def test_parse_empty(self):
        task = TaskRegistry.create("secretsdump")
        assert task.parse_output("", "") == []

class TestGetUserSPNsParser:
    def test_build_command(self):
        task = TaskRegistry.create("getuserspns")
        cmd, _ = task.build_command(
            "CORP.LOCAL",
            username="user",
            password="pass",
            dc_ip="10.0.0.1",
            request=True,
        )
        assert "impacket-GetUserSPNs" in cmd
        assert "-dc-ip 10.0.0.1" in cmd
        assert "-request" in cmd
        assert "CORP.LOCAL/user:pass" in cmd

    def test_parse_hash_output(self):
        task = TaskRegistry.create("getuserspns")
        stdout = (
            "Impacket v0.11.0\n"
            "$krb5tgs$23$*svc_sql$CORP.LOCAL$svc_sql*$aabbccdd$112233445566778899...\n"
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert isinstance(results[0], UserAccount)
        assert results[0].username == "svc_sql"
        assert results[0].domain == "CORP.LOCAL"
        assert results[0].comment == "kerberoastable"

    def test_parse_spn_table(self):
        task = TaskRegistry.create("getuserspns")
        stdout = (
            "ServicePrincipalName  Name      MemberOf  PasswordLastSet      LastLogon\n"
            "--------------------  --------  --------  -------------------  ---------\n"
            "MSSQLSvc/db01:1433    svc_sql             2024-01-15 10:00:00  <never>\n"
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert results[0].username == "svc_sql"
        assert "SPN:" in results[0].comment

    def test_parse_empty(self):
        task = TaskRegistry.create("getuserspns")
        assert task.parse_output("", "") == []

class TestGetNPUsersParser:
    def test_build_command(self):
        task = TaskRegistry.create("getnpusers")
        cmd, _ = task.build_command(
            "CORP.LOCAL", dc_ip="10.0.0.1", usersfile="users.txt", format="hashcat"
        )
        assert "impacket-GetNPUsers" in cmd
        assert "-dc-ip 10.0.0.1" in cmd
        assert "-usersfile users.txt" in cmd
        assert "CORP.LOCAL/" in cmd

    def test_parse_hash_output(self):
        task = TaskRegistry.create("getnpusers")
        stdout = (
            "Impacket v0.11.0\n"
            "$krb5asrep$23$jdoe@CORP.LOCAL:aabbccdd112233445566778899aabbccdd$ff00ff00...\n"
            "$krb5asrep$23$svc_backup@CORP.LOCAL:deadbeef$cafebabe...\n"
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, UserAccount) for r in results)
        assert results[0].username == "jdoe"
        assert results[0].domain == "CORP.LOCAL"
        assert results[0].comment == "asreproastable"
        assert results[1].username == "svc_backup"

    def test_parse_empty(self):
        task = TaskRegistry.create("getnpusers")
        assert task.parse_output("", "") == []

class TestGetTGTParser:
    def test_build_command(self):
        task = TaskRegistry.create("gettgt")
        cmd, _ = task.build_command(
            "CORP.LOCAL", username="admin", password="pass", dc_ip="10.0.0.1"
        )
        assert "impacket-getTGT" in cmd
        assert "-dc-ip 10.0.0.1" in cmd
        assert "CORP.LOCAL/admin:pass" in cmd

    def test_build_command_with_hash(self):
        task = TaskRegistry.create("gettgt")
        cmd, _ = task.build_command(
            "CORP.LOCAL", username="admin", hash="aad3b435:31d6cfe0"
        )
        assert "-hashes aad3b435:31d6cfe0" in cmd

    def test_parse_ticket_output(self):
        task = TaskRegistry.create("gettgt")
        stdout = "Impacket v0.11.0\n[*] Saving ticket in admin.ccache\n"
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert isinstance(results[0], Tag)
        assert results[0].name == "tgt_ccache"
        assert results[0].value == "admin.ccache"

    def test_parse_empty(self):
        task = TaskRegistry.create("gettgt")
        assert task.parse_output("", "") == []

class TestGetSTParser:
    def test_build_command(self):
        task = TaskRegistry.create("getst")
        cmd, _ = task.build_command(
            "CORP.LOCAL",
            username="svc_sql",
            password="pass",
            spn="cifs/dc01.corp.local",
            impersonate="administrator",
        )
        assert "impacket-getST" in cmd
        assert "-spn cifs/dc01.corp.local" in cmd
        assert "-impersonate administrator" in cmd
        assert "CORP.LOCAL/svc_sql:pass" in cmd

    def test_parse_ticket_output(self):
        task = TaskRegistry.create("getst")
        stdout = (
            "Impacket v0.11.0\n"
            "[*] Getting ST for user\n"
            "[*] Saving ticket in administrator@cifs_dc01.corp.local@CORP.LOCAL.ccache\n"
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert isinstance(results[0], Tag)
        assert results[0].name == "st_ccache"
        assert "administrator" in results[0].value
        assert results[0].value.endswith(".ccache")

    def test_parse_empty(self):
        task = TaskRegistry.create("getst")
        assert task.parse_output("", "") == []

class TestCertipyParser:
    def test_build_command(self):
        task = TaskRegistry.create("certipy")
        cmd, _ = task.build_command(
            "10.0.0.1", username="user@corp.local", password="pass", vulnerable=True
        )
        assert "certipy find" in cmd
        assert "-u user@corp.local" in cmd
        assert "-p pass" in cmd
        assert "-vulnerable" in cmd
        assert "-dc-ip 10.0.0.1" in cmd

    def test_parse_json_output(self):
        task = TaskRegistry.create("certipy")
        data = {
            "Certificate Templates": {
                "VulnTemplate": {
                    "Vulnerabilities": {"ESC1": "Enrollee supplies subject"}
                },
                "SafeTemplate": {"Vulnerabilities": {}},
            }
        }
        results = task.parse_output(json.dumps(data), "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(vulns) == 1
        assert "ESC1" in vulns[0].name
        assert "VulnTemplate" in vulns[0].description
        assert len(tags) == 2
        tpl_names = {t.value for t in tags}
        assert "VulnTemplate" in tpl_names
        assert "SafeTemplate" in tpl_names

    def test_parse_text_output(self):
        task = TaskRegistry.create("certipy")
        stdout = (
            "Certificate Authority\n"
            "  CA Name                 : CORP-CA\n"
            "Certificate Templates\n"
            "  Template Name           : VulnTemplate\n"
            "  ESC1 - Enrollee supplies subject\n"
            "  Template Name           : SafeTemplate\n"
        )
        results = task.parse_output(stdout, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(vulns) == 1
        assert "ESC1" in vulns[0].name
        ca_tags = [t for t in tags if t.name == "ca"]
        assert len(ca_tags) == 1
        assert ca_tags[0].value == "CORP-CA"

    def test_parse_empty(self):
        task = TaskRegistry.create("certipy")
        assert task.parse_output("", "") == []

class TestBloodhoundPythonParser:
    def test_build_command(self):
        task = TaskRegistry.create("bloodhound-python")
        cmd, _ = task.build_command(
            "corp.local", username="user", password="pass", collection="All"
        )
        assert "bloodhound-python" in cmd
        assert "-u user" in cmd
        assert "-p pass" in cmd
        assert "-c All" in cmd
        assert "-d corp.local" in cmd

    def test_build_command_default_collection(self):
        task = TaskRegistry.create("bloodhound-python")
        cmd, _ = task.build_command("corp.local")
        assert "-c All" in cmd

    def test_parse_info_output(self):
        task = TaskRegistry.create("bloodhound-python")
        stdout = (
            "INFO: Found AD domain: corp.local\n"
            "INFO: Found 42 users\n"
            "INFO: Found 15 groups\n"
            "INFO: Found 3 computers\n"
            "INFO: Done in 00m 05s\n"
        )
        results = task.parse_output(stdout, "")
        info_tags = [r for r in results if r.name == "collection_info"]
        status_tags = [r for r in results if r.name == "status"]
        assert (
            len(info_tags) == 4
        )
        assert len(status_tags) == 1
        assert status_tags[0].value == "completed"
        assert "42 users" in info_tags[1].value

    def test_parse_empty(self):
        task = TaskRegistry.create("bloodhound-python")
        assert task.parse_output("", "") == []

class TestLdeepParser:
    def test_build_command(self):
        task = TaskRegistry.create("ldeep")
        cmd, _ = task.build_command(
            "10.0.0.1",
            username="user",
            password="pass",
            domain="corp.local",
            action="users",
        )
        assert "ldeep ldap" in cmd
        assert "-u user" in cmd
        assert "-p pass" in cmd
        assert "-d corp.local" in cmd
        assert "-s 10.0.0.1" in cmd
        assert cmd.endswith("users")

    def test_parse_json_list(self):
        task = TaskRegistry.create("ldeep")
        data = [
            {
                "sAMAccountName": "jdoe",
                "distinguishedName": "CN=jdoe,OU=Users,DC=corp,DC=local",
            },
            {
                "sAMAccountName": "admin",
                "distinguishedName": "CN=admin,OU=Admins,DC=corp,DC=local",
            },
        ]
        results = task.parse_output(json.dumps(data), "")
        accounts = [r for r in results if isinstance(r, UserAccount)]
        assert len(accounts) == 2
        assert accounts[0].username == "jdoe"
        assert accounts[1].username == "admin"

    def test_parse_json_asreproastable(self):
        task = TaskRegistry.create("ldeep")
        data = [
            {
                "sAMAccountName": "vuln_user",
                "userAccountControl": 0x400000,
                "distinguishedName": "CN=vuln_user,DC=corp,DC=local",
            },
        ]
        results = task.parse_output(json.dumps(data), "")
        tags = [r for r in results if isinstance(r, Tag)]
        assert any(t.name == "asreproastable" and t.value == "vuln_user" for t in tags)

    def test_parse_plain_text(self):
        task = TaskRegistry.create("ldeep")
        stdout = "jdoe\nadmin\nsvc_sql\n"
        results = task.parse_output(stdout, "")
        assert len(results) == 3
        assert all(isinstance(r, UserAccount) for r in results)

    def test_parse_empty(self):
        task = TaskRegistry.create("ldeep")
        assert task.parse_output("", "") == []

class TestLdapDomainDumpParser:
    def test_build_command(self):
        task = TaskRegistry.create("ldapdomaindump")
        cmd, _ = task.build_command("10.0.0.1", username="CORP\\admin", password="pass")
        assert "ldapdomaindump" in cmd
        assert "ldap://10.0.0.1" in cmd
        assert "-u 'CORP\\admin'" in cmd or "-u CORP\\admin" in cmd

    def test_build_command_ldap_uri(self):
        task = TaskRegistry.create("ldapdomaindump")
        cmd, _ = task.build_command("ldap://10.0.0.1")
        assert "ldap://10.0.0.1" in cmd
        assert "ldap://ldap://" not in cmd

    def test_parse_json_entries(self):
        task = TaskRegistry.create("ldapdomaindump")
        data = [
            {"attributes": {"sAMAccountName": "jdoe"}},
            {"attributes": {"sAMAccountName": "admin"}},
        ]
        results = task.parse_output(json.dumps(data), "")
        accounts = [r for r in results if isinstance(r, UserAccount)]
        assert len(accounts) == 2
        assert accounts[0].username == "jdoe"

    def test_parse_text_output(self):
        task = TaskRegistry.create("ldapdomaindump")
        stdout = (
            "[*] Writing domain_users.json to loot/\n"
            "[*] Writing domain_groups.json to loot/\n"
        )
        results = task.parse_output(stdout, "")
        tags = [r for r in results if isinstance(r, Tag)]
        assert len(tags) == 2
        assert all(t.name == "output_file" for t in tags)

    def test_parse_empty(self):
        task = TaskRegistry.create("ldapdomaindump")
        assert task.parse_output("", "") == []

class TestResponderParser:
    def test_build_command(self):
        task = TaskRegistry.create("responder")
        cmd, _ = task.build_command("eth0", analyze=True)
        assert "responder" in cmd
        assert "-I eth0" in cmd
        assert "-A" in cmd

    def test_parse_ntlmv2_hash(self):
        task = TaskRegistry.create("responder")
        stdout = (
            "[SMB] NTLMv2-SSP Client   : 10.0.0.5\n"
            "[SMB] NTLMv2-SSP Username : CORP\\admin\n"
            "[SMB] NTLMv2-SSP Hash     : admin::CORP:aabbccdd:1122334455667788:0011223344\n"
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert isinstance(results[0], UserAccount)
        assert results[0].username == "admin"
        assert results[0].domain == "CORP"
        assert "aabbccdd" in results[0].hash

    def test_parse_dedup(self):
        task = TaskRegistry.create("responder")
        stdout = (
            "[SMB] NTLMv2-SSP Hash     : admin::CORP:aabbccdd:1122334455667788:00\n"
            "[SMB] NTLMv2-SSP Hash     : admin::CORP:aabbccdd:1122334455667788:00\n"
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 1

    def test_parse_empty(self):
        task = TaskRegistry.create("responder")
        assert task.parse_output("", "") == []

class TestCoercerParser:
    def test_build_command(self):
        task = TaskRegistry.create("coercer")
        cmd, _ = task.build_command(
            "10.0.0.1",
            listener="10.0.0.100",
            username="user",
            password="pass",
            domain="CORP",
        )
        assert "coercer scan" in cmd
        assert "-t 10.0.0.1" in cmd
        assert "-l 10.0.0.100" in cmd
        assert "-u user" in cmd or "user" in cmd

    def test_parse_vulnerable(self):
        task = TaskRegistry.create("coercer")
        stdout = (
            "[+] MS-EFSR (EfsRpcOpenFileRaw) on 10.0.0.1 -> VULNERABLE\n"
            "[-] MS-RPRN (RpcRemoteFindFirstPrinterChangeNotification) on 10.0.0.1 -> NOT VULNERABLE\n"
            "[+] MS-DFSNM (NetrDfsAddStdRoot) on 10.0.0.1 -> VULNERABLE\n"
        )
        results = task.parse_output(stdout, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 2
        assert "MS-EFSR" in vulns[0].name
        assert "MS-DFSNM" in vulns[1].name
        assert vulns[0].severity == "high"

    def test_parse_no_vulns(self):
        task = TaskRegistry.create("coercer")
        stdout = "[-] MS-EFSR (EfsRpcOpenFileRaw) on 10.0.0.1 -> NOT VULNERABLE\n"
        results = task.parse_output(stdout, "")
        assert results == []

    def test_parse_empty(self):
        task = TaskRegistry.create("coercer")
        assert task.parse_output("", "") == []

class TestHashcatParser:
    def test_build_command(self):
        task = TaskRegistry.create("hashcat")
        cmd, _ = task.build_command(
            "hashes.txt",
            hash_type=1000,
            attack_mode=0,
            wordlist="/usr/share/wordlists/rockyou.txt",
            force=True,
        )
        assert "hashcat" in cmd
        assert "-m 1000" in cmd
        assert "-a 0" in cmd
        assert "hashes.txt" in cmd
        assert "/usr/share/wordlists/rockyou.txt" in cmd
        assert "--force" in cmd

    def test_parse_hash_password(self):
        task = TaskRegistry.create("hashcat")
        stdout = "31d6cfe0d16ae931b73c59d7e0c089c0:password123\n"
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert isinstance(results[0], UserAccount)
        assert results[0].password == "password123"
        assert results[0].hash == "31d6cfe0d16ae931b73c59d7e0c089c0"

    def test_parse_user_hash_password(self):
        task = TaskRegistry.create("hashcat")
        stdout = "admin:31d6cfe0d16ae931b73c59d7e0c089c0:password123\n"
        results = task.parse_output(stdout, "")
        assert len(results) == 1
        assert results[0].username == "admin"
        assert results[0].password == "password123"
        assert results[0].hash == "31d6cfe0d16ae931b73c59d7e0c089c0"

    def test_parse_skips_hash_only(self):
        task = TaskRegistry.create("hashcat")
        stdout = "aad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0\n"
        results = task.parse_output(stdout, "")
        assert len(results) == 0

    def test_parse_empty(self):
        task = TaskRegistry.create("hashcat")
        assert task.parse_output("", "") == []

class TestJohnParser:
    def test_build_command(self):
        task = TaskRegistry.create("john")
        cmd, _ = task.build_command(
            "hashes.txt", wordlist="/usr/share/wordlists/rockyou.txt", format="NT"
        )
        assert "john" in cmd
        assert "--wordlist" in cmd
        assert "/usr/share/wordlists/rockyou.txt" in cmd
        assert "--format NT" in cmd
        assert "hashes.txt" in cmd

    def test_parse_show_output(self):
        task = TaskRegistry.create("john")
        stdout = (
            "admin:password123\njdoe:Summer2024!\n2 password hashes cracked, 0 left\n"
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, UserAccount) for r in results)
        assert results[0].username == "admin"
        assert results[0].password == "password123"
        assert results[1].username == "jdoe"
        assert results[1].password == "Summer2024!"

    def test_parse_skips_summary(self):
        task = TaskRegistry.create("john")
        stdout = "3 password hashes cracked, 1 left\n"
        results = task.parse_output(stdout, "")
        assert results == []

    def test_parse_empty(self):
        task = TaskRegistry.create("john")
        assert task.parse_output("", "") == []

class TestLinpeasParser:
    def test_build_command(self):
        task = TaskRegistry.create("linpeas")
        cmd, _ = task.build_command("", quiet=True, thorough=True)
        assert "linpeas.sh" in cmd
        assert "-q" in cmd
        assert "-a" in cmd

    def test_parse_cve_output(self):
        task = TaskRegistry.create("linpeas")
        stdout = (
            "\x1b[91m[!] CVE-2021-4034 - PwnKit: Local Privilege Escalation in polkit\x1b[0m\n"
            "Some normal line\n"
            "\x1b[33mCVE-2022-0847 - DirtyPipe\x1b[0m\n"
        )
        results = task.parse_output(stdout, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 2
        cve_names = {v.name for v in vulns}
        assert "CVE-2021-4034" in cve_names
        assert "CVE-2022-0847" in cve_names

    def test_parse_dedup_cves(self):
        task = TaskRegistry.create("linpeas")
        stdout = "CVE-2021-4034 PwnKit\nCVE-2021-4034 also mentioned here\n"
        results = task.parse_output(stdout, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 1

    def test_parse_empty(self):
        task = TaskRegistry.create("linpeas")
        assert task.parse_output("", "") == []

class TestWinpeasParser:
    def test_build_command(self):
        task = TaskRegistry.create("winpeas")
        cmd, _ = task.build_command("")
        assert "winPEASx64.exe" in cmd

    def test_parse_cve_output(self):
        task = TaskRegistry.create("winpeas")
        stdout = (
            "\x1b[91m  CVE-2021-36934 - HiveNightmare/SeriousSAM\x1b[0m\n"
            "  Some normal output\n"
            "\x1b[33m  CVE-2021-1675 - PrintNightmare\x1b[0m\n"
        )
        results = task.parse_output(stdout, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 2
        cve_names = {v.name for v in vulns}
        assert "CVE-2021-36934" in cve_names
        assert "CVE-2021-1675" in cve_names

    def test_parse_dedup_cves(self):
        task = TaskRegistry.create("winpeas")
        stdout = "CVE-2021-36934 first mention\nCVE-2021-36934 second mention\n"
        results = task.parse_output(stdout, "")
        vulns = [r for r in results if isinstance(r, Vulnerability)]
        assert len(vulns) == 1

    def test_parse_empty(self):
        task = TaskRegistry.create("winpeas")
        assert task.parse_output("", "") == []

class TestHydraParser:
    def test_hydra_metadata(self):
        task = TaskRegistry.create("hydra")
        assert task.name == "hydra"
        assert task.cmd == "hydra"
        assert task.category == "brute/login"
        assert task.install_cmd
        assert len(task.output_types) > 0

    def test_hydra_parse_output(self):
        stdout = "\n".join(
            [
                "Hydra v9.5 starting...",
                "[DATA] max 16 tasks per 1 server",
                "[22][ssh] host: 10.0.0.1   login: root   password: toor",
                "[22][ssh] host: 10.0.0.1   login: admin   password: admin123",
                "[STATUS] attack finished for 10.0.0.1",
            ]
        )
        task = TaskRegistry.create("hydra")
        results = task.parse_output(stdout, "")
        from ofx.tasks.output_types import UserAccount

        users = [r for r in results if isinstance(r, UserAccount)]
        assert len(users) == 2
        assert users[0].username == "root"
        assert users[0].password == "toor"
        assert users[0].host == "10.0.0.1"
        assert "port=22" in users[0].comment
        assert "service=ssh" in users[0].comment
        assert users[1].username == "admin"
        assert users[1].password == "admin123"

    def test_hydra_parse_empty(self):
        task = TaskRegistry.create("hydra")
        assert task.parse_output("", "") == []

    def test_hydra_build_command(self):
        task = TaskRegistry.create("hydra")
        cmd, _ = task.build_command(
            "10.0.0.1",
            service="ssh",
            login="admin",
            password_file="/tmp/passwords.txt",
            threads=16,
            force=True,
        )
        assert "hydra" in cmd
        assert "-l admin" in cmd
        assert "-P /tmp/passwords.txt" in cmd
        assert "-t 16" in cmd
        assert "-f" in cmd
        assert "10.0.0.1" in cmd
        assert cmd.endswith("ssh")

class TestBrutusParser:
    def test_brutus_metadata(self):
        task = TaskRegistry.create("brutus")
        assert task.name == "brutus"
        assert task.cmd == "brutus"
        assert task.category == "brute/credential"
        assert task.install_cmd
        assert UserAccount in task.output_types

    def test_brutus_parse_line_full(self):
        task = TaskRegistry.create("brutus")
        line = json.dumps(
            {
                "host": "192.168.1.1",
                "port": 22,
                "service": "ssh",
                "username": "admin",
                "password": "admin123",
                "banner": "SSH-2.0-OpenSSH_8.9",
            }
        )
        results = task.parse_line(line)
        assert len(results) == 1
        ua = results[0]
        assert isinstance(ua, UserAccount)
        assert ua.username == "admin"
        assert ua.password == "admin123"
        assert ua.host == "192.168.1.1:22"
        assert ua.source == "brutus/ssh"
        assert ua.extra_data["service"] == "ssh"
        assert ua.extra_data["port"] == 22
        assert ua.extra_data["banner"] == "SSH-2.0-OpenSSH_8.9"

    def test_brutus_parse_line_alt_keys(self):
        task = TaskRegistry.create("brutus")
        line = json.dumps(
            {"ip": "10.0.0.5", "login": "root", "pass": "toor", "protocol": "ftp"}
        )
        results = task.parse_line(line)
        assert len(results) == 1
        assert results[0].username == "root"
        assert results[0].password == "toor"
        assert results[0].host == "10.0.0.5"
        assert results[0].source == "brutus/ftp"

    def test_brutus_parse_line_no_username(self):
        task = TaskRegistry.create("brutus")
        line = json.dumps({"host": "10.0.0.1", "port": 22, "password": "test"})
        assert task.parse_line(line) == []

    def test_brutus_parse_line_invalid(self):
        task = TaskRegistry.create("brutus")
        assert task.parse_line("") == []
        assert task.parse_line("not json") == []
        assert task.parse_line("[info] bruting...") == []
        assert task.parse_line("{}") == []

    def test_brutus_parse_output_stdout(self):
        task = TaskRegistry.create("brutus")
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "host": "10.0.0.1",
                        "port": 22,
                        "username": "admin",
                        "password": "admin",
                        "service": "ssh",
                    }
                ),
                json.dumps(
                    {
                        "host": "10.0.0.2",
                        "port": 3306,
                        "username": "root",
                        "password": "",
                        "service": "mysql",
                    }
                ),
                "[info] done",
            ]
        )
        results = task.parse_output(stdout, "")
        assert len(results) == 2
        assert all(isinstance(r, UserAccount) for r in results)
        assert results[0].username == "admin"
        assert results[1].username == "root"

    def test_brutus_parse_output_file(self, tmp_path):
        task = TaskRegistry.create("brutus")
        f = tmp_path / "out.jsonl"
        f.write_text(
            json.dumps(
                {
                    "host": "10.0.0.1",
                    "port": 5432,
                    "username": "postgres",
                    "password": "postgres",
                    "service": "postgresql",
                }
            )
        )
        results = task.parse_output("", "", output_file=f)
        assert len(results) == 1
        assert results[0].username == "postgres"

    def test_brutus_parse_empty(self):
        task = TaskRegistry.create("brutus")
        assert task.parse_output("", "") == []

    def test_brutus_streaming(self):
        task = TaskRegistry.create("brutus")
        assert task.supports_streaming is True

class TestZombieParser:
    def test_zombie_parse_json_array(self):
        task = TaskRegistry.create("zombie")
        stdout = json.dumps(
            [
                {
                    "host": "10.0.0.1",
                    "user": "admin",
                    "password": "admin",
                    "service": "ssh",
                    "port": 22,
                    "status": "success",
                }
            ]
        )

        results = task.parse_output(stdout, "")

        assert len(results) == 1
        assert results[0].username == "admin"
        assert results[0].comment == "service=ssh port=22"

    def test_zombie_parse_mixed_jsonl_and_string_output(self):
        task = TaskRegistry.create("zombie")
        stdout = "\n".join(
            [
                json.dumps({"status": "metadata"}),
                "ssh://root:toor@10.0.0.5:22",
            ]
        )

        results = task.parse_output(stdout, "")

        assert len(results) == 1
        assert results[0].username == "root"
        assert results[0].password == "toor"
        assert results[0].host == "10.0.0.5"
