from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from ofx.api.creds.exegol_history import Credential, ExegolHistoryDB, Host


@dataclass
class FakeEntry:
    uuid: UUID
    title: str
    username: str
    password: str
    url: str
    notes: str
    group: "FakeGroup"
    custom_properties: dict


class FakeGroup:
    def __init__(self, name: str):
        self.name = name
        self.entries: list[FakeEntry] = []


class FakeKeePass:
    def __init__(self):
        self.groups: dict[str, FakeGroup] = {}
        self.root_group = FakeGroup("Root")

    def find_groups(self, name: str, first: bool = True):
        return self.groups.get(name)

    def find_entries(self, uuid: UUID, first: bool = True):
        for group in self.groups.values():
            for entry in group.entries:
                if entry.uuid == uuid:
                    return entry
        return None

    def add_group(self, parent, name: str):
        group = FakeGroup(name)
        self.groups[name] = group
        return group

    def add_entry(self, group: FakeGroup, title: str, username: str, password: str, url: str, notes: str):
        entry = FakeEntry(
            uuid=uuid4(),
            title=title,
            username=username,
            password=password,
            url=url,
            notes=notes,
            group=group,
            custom_properties={},
        )
        group.entries.append(entry)
        return entry

    def delete_entry(self, entry: FakeEntry):
        entry.group.entries.remove(entry)

    def save(self) -> None:
        return None


def _install_fake_pykeepass(monkeypatch: pytest.MonkeyPatch, kp: FakeKeePass) -> None:
    fake_module = types.ModuleType("pykeepass")
    fake_module.PyKeePass = lambda *args, **kwargs: kp
    monkeypatch.setitem(sys.modules, "pykeepass", fake_module)


def _make_db(tmp_path, monkeypatch: pytest.MonkeyPatch, kp: FakeKeePass) -> ExegolHistoryDB:
    db_path = tmp_path / "db.kdbx"
    key_path = tmp_path / "db.key"
    db_path.write_text("x")
    key_path.write_text("y")
    _install_fake_pykeepass(monkeypatch, kp)
    return ExegolHistoryDB(db_path=db_path, key_path=key_path)


def _add_entry(group: FakeGroup, title: str, username: str, password: str, url: str, notes: str):
    entry = FakeEntry(
        uuid=uuid4(),
        title=title,
        username=username,
        password=password,
        url=url,
        notes=notes,
        group=group,
        custom_properties={},
    )
    group.entries.append(entry)
    return entry


def test_list_get_and_search(monkeypatch: pytest.MonkeyPatch, tmp_path):
    kp = FakeKeePass()
    creds_group = FakeGroup(Credential.GROUP_NAME)
    host_group = FakeGroup(Host.GROUP_NAME)
    kp.groups[creds_group.name] = creds_group
    kp.groups[host_group.name] = host_group

    cred_entry = _add_entry(creds_group, "alice", "alice", "pw", "", "svc=ssh")
    cred_entry.custom_properties[Credential.EXEGOL_DB_DOMAIN_PROPERTY] = "corp"
    cred_entry.custom_properties[Credential.EXEGOL_DB_HASH_PROPERTY] = "NTLM"
    cred_entry.custom_properties[Credential.EXEGOL_DB_COMMENT_PROPERTY] = "svc=ssh"

    host_entry = _add_entry(host_group, "10.0.0.1", "", "", "10.0.0.1", "dc host")
    host_entry.custom_properties[Host.EXEGOL_DB_HOSTNAME_PROPERTY] = "dc01"
    host_entry.custom_properties[Host.EXEGOL_DB_ROLE_PROPERTY] = "DC"
    host_entry.custom_properties[Host.EXEGOL_DB_COMMENT_PROPERTY] = "critical"

    db = _make_db(tmp_path, monkeypatch, kp)

    creds = db.list_credentials()
    hosts = db.list_hosts()
    assert len(creds) == 1
    assert len(hosts) == 1
    assert creds[0].username == "alice"
    assert hosts[0].hostname == "dc01"

    by_id = db.get_credential_by_id("1")
    assert by_id is not None
    assert by_id.domain == "corp"

    host_by_id = db.get_host_by_id("1")
    assert host_by_id is not None
    assert host_by_id.ip == "10.0.0.1"

    entry = db.get_entry_by_id("1", group=Host.GROUP_NAME)
    assert isinstance(entry, Host)

    assert db.get_credential("alice") is not None
    assert db.get_host("10.0.0.1") is not None

    assert db.search_credentials("corp")
    assert db.search_hosts("dc01")
    assert db.search_by_group(Credential.GROUP_NAME, "ssh")
    assert db.search_all("critical")


def test_add_update_delete(monkeypatch: pytest.MonkeyPatch, tmp_path):
    kp = FakeKeePass()
    db = _make_db(tmp_path, monkeypatch, kp)

    cred = db.add_credential("bob", password="pw", hash_value="hash", domain="lab", comment="svc")
    assert cred.username == "bob"
    assert Credential.GROUP_NAME in kp.groups
    assert cred.hash == "hash"

    host = db.add_host("10.0.0.9", hostname="wks", role="WKS", comment="ok")
    assert host.hostname == "wks"
    assert Host.GROUP_NAME in kp.groups

    assert db.update_credential_comment(cred.id, "new") is True
    updated = db.get_credential_by_id(cred.id)
    assert updated is not None
    assert updated.comment == "new"

    assert db.update_host_comment(host.id, "updated") is True
    updated_host = db.get_host_by_id(host.id)
    assert updated_host is not None
    assert updated_host.comment == "updated"

    assert db.delete(cred.id) is True
    assert db.get_credential_by_id(cred.id) is None
    assert db.delete("not-a-uuid") is False
