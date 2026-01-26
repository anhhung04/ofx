"""Access credentials/hosts from the Exegol History KeePass database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from uuid import UUID

__all__ = ["Credential", "Host", "ExegolHistoryDB"]


@dataclass
class Credential:
    """Represents a credential entry in the KeePass database."""

    GROUP_NAME: ClassVar[str] = "Credentials"
    EXEGOL_DB_HASH_PROPERTY: ClassVar[str] = "hash"
    EXEGOL_DB_DOMAIN_PROPERTY: ClassVar[str] = "domain"
    EXEGOL_DB_COMMENT_PROPERTY: ClassVar[str] = "comment"
    REDACT_SEPARATOR: ClassVar[str] = "*"
    HEADERS: ClassVar[list[str]] = ["username", "password", "hash", "domain", "comment"]

    id: str = ""
    username: str = ""
    password: str = ""
    hash: str = ""
    domain: str = ""
    comment: str = ""

    def __iter__(self):
        return iter([self.id, self.username, self.password, self.hash, self.domain, self.comment])


@dataclass
class Host:
    """Represents a host entry in the KeePass database."""

    GROUP_NAME: ClassVar[str] = "Hosts"
    EXEGOL_DB_ROLE_PROPERTY: ClassVar[str] = "role"
    EXEGOL_DB_HOSTNAME_PROPERTY: ClassVar[str] = "hostname"
    EXEGOL_DB_COMMENT_PROPERTY: ClassVar[str] = "comment"
    HEADERS: ClassVar[list[str]] = ["ip", "hostname", "role", "comment"]

    id: str = ""
    ip: str = ""
    hostname: str = ""
    role: str = ""
    comment: str = ""

    def __iter__(self):
        return iter([self.id, self.ip, self.hostname, self.role, self.comment])


class ExegolHistoryDB:
    """KeePass-backed credential/host store for Exegol History."""

    def __init__(
        self,
        db_path: str | Path = "~/.exh/DB.kdbx",
        key_path: str | Path = "~/.exh/db.key",
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.key_path = Path(key_path).expanduser()

        try:
            from pykeepass import PyKeePass  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise ImportError(
                "Exegol History support requires the 'pykeepass' package. "
                "Install it with: pip install pykeepass"
            ) from exc

        if not self.db_path.exists():
            raise FileNotFoundError(f"KeePass database not found: {self.db_path}")
        if not self.key_path.exists():
            raise FileNotFoundError(f"KeePass key not found: {self.key_path}")

        self._kp = PyKeePass(str(self.db_path), keyfile=str(self.key_path))

    def _group(self, name: str):
        return self._kp.find_groups(name=name, first=True)

    def _get_entry_by_uuid(self, entry_id: str):
        try:
            uuid_value = UUID(entry_id)
        except ValueError:
            return None
        return self._kp.find_entries(uuid=uuid_value, first=True)

    def _get_entry_by_index(self, group_name: str, entry_id: int):
        grp = self._group(group_name)
        if grp is None:
            return None
        if entry_id < 1 or entry_id > len(grp.entries):
            return None
        return grp.entries[entry_id - 1]

    def _parse_int_id(self, entry_id: str | int) -> int | None:
        if isinstance(entry_id, int):
            return entry_id
        if isinstance(entry_id, str) and entry_id.isdigit():
            return int(entry_id)
        return None

    def list_credentials(self) -> list[Credential]:
        grp = self._group(Credential.GROUP_NAME)
        if grp is None:
            return []
        return [self._to_credential(e, index=idx + 1) for idx, e in enumerate(grp.entries)]

    def list_hosts(self) -> list[Host]:
        grp = self._group(Host.GROUP_NAME)
        if grp is None:
            return []
        return [self._to_host(e, index=idx + 1) for idx, e in enumerate(grp.entries)]

    def get_credential_by_id(self, entry_id: str) -> Credential | None:
        int_id = self._parse_int_id(entry_id)
        if int_id is not None:
            entry = self._get_entry_by_index(Credential.GROUP_NAME, int_id)
            if entry is None:
                return None
            return self._to_credential(entry, index=int_id)
        entry = self._get_entry_by_uuid(entry_id)
        if entry is None:
            return None
        return self._to_credential(entry)

    def get_host_by_id(self, entry_id: str) -> Host | None:
        int_id = self._parse_int_id(entry_id)
        if int_id is not None:
            entry = self._get_entry_by_index(Host.GROUP_NAME, int_id)
            if entry is None:
                return None
            return self._to_host(entry, index=int_id)
        entry = self._get_entry_by_uuid(entry_id)
        if entry is None:
            return None
        return self._to_host(entry)

    def get_credential(self, username: str) -> Credential | None:
        """Fetch the first credential entry by username or title."""
        grp = self._group(Credential.GROUP_NAME)
        if grp is None:
            return None
        for entry in grp.entries:
            if entry.username == username or entry.title == username:
                return self._to_credential(entry)
        return None

    def get_host(self, ip: str) -> Host | None:
        """Fetch the first host entry by ip/url/title."""
        grp = self._group(Host.GROUP_NAME)
        if grp is None:
            return None
        for entry in grp.entries:
            if entry.url == ip or entry.title == ip:
                return self._to_host(entry)
        return None

    def get_entry_by_id(
        self,
        entry_id: str,
        group: str | None = None,
    ) -> Credential | Host | None:
        """Fetch an entry by id and return the normalized record."""
        int_id = self._parse_int_id(entry_id)
        if int_id is not None:
            groups = [group] if group else [Credential.GROUP_NAME, Host.GROUP_NAME]
            for group_name in groups:
                if group_name is None:
                    continue
                entry = self._get_entry_by_index(group_name, int_id)
                if entry is None:
                    continue
                if group_name == Credential.GROUP_NAME:
                    return self._to_credential(entry, index=int_id)
                if group_name == Host.GROUP_NAME:
                    return self._to_host(entry, index=int_id)
            return None
        entry = self._get_entry_by_uuid(entry_id)
        if entry is None:
            return None
        group_name = entry.group.name if entry.group else ""
        if group_name == Credential.GROUP_NAME:
            return self._to_credential(entry)
        if group_name == Host.GROUP_NAME:
            return self._to_host(entry)
        return None

    def search_credentials(self, query: str) -> list[Credential]:
        """Search credential entries by username, domain, hash, or comment."""
        results: list[Credential] = []
        q = query.lower()
        for entry in self.list_credentials():
            haystack = " ".join(
                filter(None, [entry.username, entry.domain, entry.hash, entry.comment])
            ).lower()
            if q in haystack:
                results.append(entry)
        return results

    def search_hosts(self, query: str) -> list[Host]:
        """Search host entries by ip, hostname, role, or comment."""
        results: list[Host] = []
        q = query.lower()
        for entry in self.list_hosts():
            haystack = " ".join(
                filter(None, [entry.ip, entry.hostname, entry.role, entry.comment])
            ).lower()
            if q in haystack:
                results.append(entry)
        return results

    def search_by_group(self, group: str, query: str) -> list[Credential | Host]:
        """Search within a specific group by title, username, url, or comment."""
        grp = self._group(group)
        if grp is None:
            return []
        results: list[Credential | Host] = []
        q = query.lower()
        for entry in grp.entries:
            props = entry.custom_properties or {}
            comment = (
                props.get(Credential.EXEGOL_DB_COMMENT_PROPERTY, "")
                or entry.notes
                or ""
            )
            haystack = " ".join(
                filter(None, [entry.title, entry.username, entry.url, comment])
            ).lower()
            if q in haystack:
                if group == Credential.GROUP_NAME:
                    results.append(self._to_credential(entry))
                elif group == Host.GROUP_NAME:
                    results.append(self._to_host(entry))
        return results

    def search_all(self, query: str) -> list[Credential | Host]:
        """Search across both credential and host groups."""
        results: list[Credential | Host] = []
        results.extend(self.search_credentials(query))
        results.extend(self.search_hosts(query))
        return results

    def add_credential(
        self,
        username: str,
        password: str = "",
        hash_value: str = "",
        domain: str = "",
        comment: str = "",
    ) -> Credential:
        grp = self._group(Credential.GROUP_NAME)
        if grp is None:
            grp = self._kp.add_group(self._kp.root_group, Credential.GROUP_NAME)
        entry = self._kp.add_entry(
            grp,
            title=username,
            username=username,
            password=password,
            url="",
            notes="",
        )
        if hash_value:
            entry.custom_properties[Credential.EXEGOL_DB_HASH_PROPERTY] = hash_value
        if domain:
            entry.custom_properties[Credential.EXEGOL_DB_DOMAIN_PROPERTY] = domain
        if comment:
            entry.custom_properties[Credential.EXEGOL_DB_COMMENT_PROPERTY] = comment
        self._kp.save()
        return self._to_credential(entry, index=len(grp.entries))

    def add_host(
        self,
        ip: str,
        hostname: str = "",
        role: str = "",
        comment: str = "",
    ) -> Host:
        grp = self._group(Host.GROUP_NAME)
        if grp is None:
            grp = self._kp.add_group(self._kp.root_group, Host.GROUP_NAME)
        entry = self._kp.add_entry(
            grp,
            title=ip,
            username="",
            password="",
            url=ip,
            notes="",
        )
        if hostname:
            entry.custom_properties[Host.EXEGOL_DB_HOSTNAME_PROPERTY] = hostname
        if role:
            entry.custom_properties[Host.EXEGOL_DB_ROLE_PROPERTY] = role
        if comment:
            entry.custom_properties[Host.EXEGOL_DB_COMMENT_PROPERTY] = comment
        self._kp.save()
        return self._to_host(entry, index=len(grp.entries))

    def update_credential_comment(self, entry_id: str, comment: str) -> bool:
        int_id = self._parse_int_id(entry_id)
        if int_id is not None:
            entry = self._get_entry_by_index(Credential.GROUP_NAME, int_id)
        else:
            entry = self._get_entry_by_uuid(entry_id)
        if entry is None:
            return False
        entry.custom_properties[Credential.EXEGOL_DB_COMMENT_PROPERTY] = comment
        self._kp.save()
        return True

    def update_host_comment(self, entry_id: str, comment: str) -> bool:
        int_id = self._parse_int_id(entry_id)
        if int_id is not None:
            entry = self._get_entry_by_index(Host.GROUP_NAME, int_id)
        else:
            entry = self._get_entry_by_uuid(entry_id)
        if entry is None:
            return False
        entry.custom_properties[Host.EXEGOL_DB_COMMENT_PROPERTY] = comment
        self._kp.save()
        return True

    def delete(self, entry_id: str) -> bool:
        int_id = self._parse_int_id(entry_id)
        if int_id is not None:
            entry = self._get_entry_by_index(Credential.GROUP_NAME, int_id)
            if entry is None:
                entry = self._get_entry_by_index(Host.GROUP_NAME, int_id)
        else:
            entry = self._get_entry_by_uuid(entry_id)
        if entry is None:
            return False
        self._kp.delete_entry(entry)
        self._kp.save()
        return True

    def _to_credential(self, entry, index: int | None = None) -> Credential:
        props = entry.custom_properties or {}
        return Credential(
            id=str(index) if index is not None else str(entry.uuid),
            username=entry.username or entry.title or "",
            password=entry.password or "",
            hash=props.get(Credential.EXEGOL_DB_HASH_PROPERTY, ""),
            domain=props.get(Credential.EXEGOL_DB_DOMAIN_PROPERTY, ""),
            comment=props.get(Credential.EXEGOL_DB_COMMENT_PROPERTY, "") or entry.notes or "",
        )

    def _to_host(self, entry, index: int | None = None) -> Host:
        props = entry.custom_properties or {}
        return Host(
            id=str(index) if index is not None else str(entry.uuid),
            ip=entry.url or entry.title or "",
            hostname=props.get(Host.EXEGOL_DB_HOSTNAME_PROPERTY, ""),
            role=props.get(Host.EXEGOL_DB_ROLE_PROPERTY, ""),
            comment=props.get(Host.EXEGOL_DB_COMMENT_PROPERTY, "") or entry.notes or "",
        )
