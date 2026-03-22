"""Unified output types for structured tool results.

Inspired by secator's output type system, these Pydantic models provide
a normalized schema for security tool output. Each type has a ``_type``
discriminator and a ``_uuid`` property used for deduplication.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Vulnerability severity levels."""

    UNKNOWN = "unknown"
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    """Confidence level for findings."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OutputType(BaseModel):
    """Base class for all structured output types."""

    _type: str = "base"
    extra_data: dict[str, Any] = Field(default_factory=dict)

    @property
    def _uuid(self) -> str:
        """Unique identifier for deduplication based on compare-relevant fields."""
        compare_fields = {
            k: v
            for k, v in self.model_dump().items()
            if k != "extra_data" and v not in (None, "", 0, [], {}, False)
        }
        raw = "|".join(f"{k}={v}" for k, v in sorted(compare_fields.items()))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict with _type discriminator included."""
        data = self.model_dump()
        data["_type"] = self._type
        data["_uuid"] = self._uuid
        return data


class Ip(OutputType):
    """An IP address discovered during scanning."""

    _type: str = "ip"
    ip: str
    host: str = ""
    alive: bool = False
    protocol: str = "IPv4"


class Port(OutputType):
    """An open port discovered during scanning."""

    _type: str = "port"
    port: int
    ip: str
    host: str = ""
    state: str = "open"
    protocol: str = "tcp"
    service_name: str = ""
    cpes: list[str] = Field(default_factory=list)

    @property
    def host_port(self) -> str:
        """Return host:port string for chaining into HTTP probers."""
        h = self.host or self.ip
        return f"{h}:{self.port}"


class Subdomain(OutputType):
    """A subdomain discovered during enumeration."""

    _type: str = "subdomain"
    host: str
    domain: str = ""
    sources: list[str] = Field(default_factory=list)


class Url(OutputType):
    """A URL discovered or probed."""

    _type: str = "url"
    url: str
    host: str = ""
    status_code: int = 0
    title: str = ""
    content_type: str = ""
    content_length: int = 0
    tech: list[str] = Field(default_factory=list)
    webserver: str = ""
    method: str = ""
    words: int = 0
    lines: int = 0


class Vulnerability(OutputType):
    """A vulnerability discovered during scanning."""

    _type: str = "vulnerability"
    name: str
    id: str = ""
    matched_at: str = ""
    severity: Severity = Severity.UNKNOWN
    confidence: Confidence = Confidence.LOW
    provider: str = ""
    description: str = ""
    cvss_score: float = 0.0
    tags: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class Tag(OutputType):
    """A tag/label discovered (tech, WAF, etc.)."""

    _type: str = "tag"
    name: str
    value: str = ""
    match: str = ""
    category: str = "general"


class Record(OutputType):
    """A DNS record."""

    _type: str = "record"
    name: str
    type: str
    host: str = ""


class Domain(OutputType):
    """A domain with registration info."""

    _type: str = "domain"
    domain: str
    registrar: str = ""
    alive: bool = False
    creation_date: str = ""
    expiration_date: str = ""


class Certificate(OutputType):
    """A TLS/SSL certificate."""

    _type: str = "certificate"
    host: str
    fingerprint_sha256: str = ""
    subject_cn: str = ""
    subject_an: list[str] = Field(default_factory=list)
    issuer_cn: str = ""
    not_before: str = ""
    not_after: str = ""
    self_signed: bool = True


class Exploit(OutputType):
    """An exploit reference found for a target."""

    _type: str = "exploit"
    name: str
    provider: str = ""
    id: str = ""
    matched_at: str = ""
    confidence: Confidence = Confidence.LOW
    reference: str = ""
    cves: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class UserAccount(OutputType):
    """A user account / credential discovered during enumeration or exploitation.

    Bridges to ``ofx.api.creds.exegol_history.Credential`` for storage in
    KeePass-backed credential databases.
    """

    _type: str = "user_account"
    username: str
    password: str = ""
    hash: str = ""
    domain: str = ""
    host: str = ""
    account_type: str = ""  # local, domain, service, machine, ...
    privilege_level: str = ""  # user, admin, system, root, ...
    enabled: bool = True
    groups: list[str] = Field(default_factory=list)
    source: str = ""
    comment: str = ""

    def to_credential(self):
        """Convert to ``ofx.api.creds.exegol_history.Credential`` dataclass."""
        from ofx.api.creds.exegol_history import Credential

        parts = []
        if self.account_type:
            parts.append(f"type={self.account_type}")
        if self.privilege_level:
            parts.append(f"priv={self.privilege_level}")
        if self.host:
            parts.append(f"host={self.host}")
        if self.source:
            parts.append(f"source={self.source}")
        if self.comment:
            parts.append(self.comment)

        return Credential(
            username=self.username,
            password=self.password,
            hash=self.hash,
            domain=self.domain,
            comment="; ".join(parts) if parts else "",
        )

    @classmethod
    def from_credential(cls, cred, host: str = "", source: str = "") -> "UserAccount":
        """Create from an ``ofx.api.creds.exegol_history.Credential``."""
        return cls(
            username=cred.username,
            password=cred.password,
            hash=cred.hash,
            domain=cred.domain,
            host=host,
            source=source,
            comment=cred.comment,
        )


# Lookup for resolving type names to classes
OUTPUT_TYPE_MAP: dict[str, type[OutputType]] = {
    "ip": Ip,
    "port": Port,
    "subdomain": Subdomain,
    "url": Url,
    "vulnerability": Vulnerability,
    "tag": Tag,
    "record": Record,
    "domain": Domain,
    "certificate": Certificate,
    "exploit": Exploit,
    "user_account": UserAccount,
}
