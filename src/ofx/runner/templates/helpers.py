"""Template helper function factories.

Each factory returns a ``dict[str, Any]`` of named helpers that are
injected into the Jinja2 template environment.  Grouping by domain
makes the helpers independently testable and keeps ``get_support_functions()``
in *resolver.py* short.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import re
import secrets
import socket
import string
import uuid as _uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

_logger = logging.getLogger("ofx.templates")


# ── File I/O ─────────────────────────────────────────────────────────────
def _file_helpers() -> dict[str, Any]:
    def _read_file(path: str) -> str:
        p = Path(path)
        return p.read_text() if p.exists() else ""

    def _write_file(path: str, content: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def _append_file(path: str, content: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(content)

    def _file_lines(path: str) -> list[str]:
        p = Path(path)
        return p.read_text().splitlines() if p.exists() else []

    return {
        "file_read": _read_file,
        "file_write": _write_file,
        "file_append": _append_file,
        "file_lines": _file_lines,
        "file_exists": lambda path: Path(path).exists(),
        "is_file": lambda path: Path(path).is_file(),
        "is_dir": lambda path: Path(path).is_dir(),
    }


# ── Paths ────────────────────────────────────────────────────────────────
def _path_helpers() -> dict[str, Any]:
    return {
        "join_path": lambda *parts: str(Path(*parts)),
        "basename": lambda path: Path(path).name,
        "dirname": lambda path: str(Path(path).parent),
        "glob": lambda pattern, directory=".": [str(p) for p in Path(directory).glob(pattern)],
        "cwd": lambda: str(Path.cwd()),
        "home": lambda: str(Path.home()),
    }


# ── String encoding ─────────────────────────────────────────────────────
def _encoding_helpers() -> dict[str, Any]:
    return {
        "b64encode": lambda s: base64.b64encode(s.encode()).decode(),
        "b64decode": lambda s: base64.b64decode(s.encode()).decode(),
        "url_encode": lambda s: quote(s, safe=""),
        "url_decode": lambda s: unquote(s),
        "hex_encode": lambda s: s.encode().hex(),
        "hex_decode": lambda s: bytes.fromhex(s).decode(),
    }


# ── Hashing ──────────────────────────────────────────────────────────────
def _hash_helpers() -> dict[str, Any]:
    def _make_hasher(algo: str):
        def _hash(s: str) -> str:
            return hashlib.new(algo, s.encode()).hexdigest()
        return _hash

    return {
        "md5": _make_hasher("md5"),
        "sha1": _make_hasher("sha1"),
        "sha256": _make_hasher("sha256"),
    }


# ── Random generators ───────────────────────────────────────────────────
def _random_helpers() -> dict[str, Any]:
    def _random_string(length: int = 8, charset: str = "alphanumeric") -> str:
        charsets = {
            "alpha": string.ascii_letters,
            "numeric": string.digits,
            "hex": string.hexdigits[:16],
        }
        chars = charsets.get(charset, string.ascii_letters + string.digits)
        return "".join(random.choices(chars, k=length))

    return {
        "random_string": _random_string,
        "random_int": lambda min_val=0, max_val=100: random.randint(min_val, max_val),
        "random_port": lambda start=1024, end=65535: random.randint(start, end),
        "uuid": lambda: str(_uuid.uuid4()),
        "token": lambda n=32: secrets.token_urlsafe(n),
    }


# ── Network ──────────────────────────────────────────────────────────────
def _network_helpers() -> dict[str, Any]:
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            _logger.debug("local_ip() socket probe failed", exc_info=True)
            return "127.0.0.1"

    def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            result = s.connect_ex((host, port))
            s.close()
            return result == 0
        except Exception:
            _logger.debug("is_port_open(%s, %s) failed", host, port, exc_info=True)
            return False

    return {
        "local_ip": _get_local_ip,
        "is_port_open": _is_port_open,
    }


# ── Date / time ──────────────────────────────────────────────────────────
def _datetime_helpers() -> dict[str, Any]:
    return {
        "now": lambda fmt="%Y-%m-%d %H:%M:%S": datetime.now().strftime(fmt),
        "timestamp": lambda: int(datetime.now().timestamp()),
    }


# ── JSON ─────────────────────────────────────────────────────────────────
def _json_helpers() -> dict[str, Any]:
    def _to_json(obj: Any) -> str:
        try:
            return json.dumps(obj, default=str)
        except (TypeError, ValueError):
            return ""

    def _from_json(s: str) -> Any:
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    return {
        "to_json": _to_json,
        "from_json": _from_json,
    }


# ── Regex ────────────────────────────────────────────────────────────────
def _regex_helpers() -> dict[str, Any]:
    return {
        "regex_match": lambda pattern, s: bool(re.match(pattern, s)),
        "regex_search": lambda pattern, s: bool(re.search(pattern, s)),
        "regex_findall": lambda pattern, s: re.findall(pattern, s),
        "regex_sub": lambda pattern, repl, s: re.sub(pattern, repl, s),
    }


# ── Task typed-output filters ───────────────────────────────────────────
_TYPE_FILTER_MAP: dict[str, str] = {
    "ports": "port",
    "urls": "url",
    "vulns": "vulnerability",
    "subdomains": "subdomain",
    "ips": "ip",
    "tags": "tag",
    "records": "record",
    "domains": "domain",
    "users": "user_account",
    "certs": "certificate",
    "exploits": "exploit",
}


def _type_filter_helpers() -> dict[str, Any]:
    def _of_type(items: list, type_name: str) -> list:
        if not isinstance(items, list):
            return []
        return [i for i in items if isinstance(i, dict) and i.get("_type") == type_name]

    def _make_type_filter(type_name: str):
        def _filter(items: list) -> list:
            return _of_type(items, type_name)
        return _filter

    return {
        "of_type": _of_type,
        **{name: _make_type_filter(tname) for name, tname in _TYPE_FILTER_MAP.items()},
    }


# ── ASM integration ─────────────────────────────────────────────────────
def _asm_helpers() -> dict[str, Any]:
    def _asm_resolve_scope(client: Any, scope_ref: str) -> str:
        if not scope_ref:
            from ofx.asm.config import get_asm_config
            scope_ref = get_asm_config().default_scope
        if not scope_ref:
            raise ValueError("No ASM scope specified")
        if len(scope_ref) >= 32 and "-" in scope_ref:
            return scope_ref
        found = client.find_scope(scope_ref)
        if found:
            return found.id
        raise ValueError(f"ASM scope '{scope_ref}' not found")

    def _asm_targets(scope: str = "", effective: bool = True, target_type: str = "") -> list[str]:
        try:
            from ofx.asm.config import get_asm_client
            client = get_asm_client()
        except Exception:
            _logger.debug("ASM client unavailable for asm_targets()", exc_info=True)
            return []
        try:
            scope_id = _asm_resolve_scope(client, scope)
            if effective:
                raw = client.effective_targets(scope_id)
                return [
                    t.value for t in raw
                    if not t.excluded and (not target_type or t.target_type == target_type)
                ]
            else:
                raw_t = client.list_targets(scope_id)
                return [
                    t.value for t in raw_t
                    if t.enabled and (not target_type or t.target_type == target_type)
                ]
        except Exception:
            _logger.debug("asm_targets() query failed", exc_info=True)
            return []

    def _asm_push(items: list, scope: str = "", source: str = "ofx") -> int:
        try:
            from ofx.asm.config import get_asm_client
            from ofx.asm.export import batch_convert
            client = get_asm_client()
        except Exception:
            _logger.debug("ASM client unavailable for asm_push()", exc_info=True)
            return 0
        try:
            scope_id = _asm_resolve_scope(client, scope)
            assets, _ = batch_convert(items, source=source)
            if not assets:
                return 0
            result = client.import_generic(scope_id, assets)
            return result.get("imported", 0)
        except Exception:
            _logger.debug("asm_push() failed", exc_info=True)
            return 0

    def _asm_scopes() -> list[dict]:
        try:
            from ofx.asm.config import get_asm_client
            client = get_asm_client()
            return [s.model_dump() for s in client.list_scopes()]
        except Exception:
            _logger.debug("asm_scopes() failed", exc_info=True)
            return []

    return {
        "asm_targets": _asm_targets,
        "asm_push": _asm_push,
        "asm_scopes": _asm_scopes,
    }


# ── Public aggregator ───────────────────────────────────────────────────
def build_all_helpers() -> dict[str, Any]:
    """Aggregate every helper group into a single dict.

    Called by :pymethod:`TemplateResolver.get_support_functions` and also
    usable in tests for direct validation.
    """
    from ofx.runner.commands.shell_functions import get_shell_exports
    from ofx.runner.execution.findings_export import export_typed_outputs
    from ofx.settings import IS_WINDOWS

    helpers: dict[str, Any] = {}
    helpers.update(get_shell_exports())
    helpers.update(_file_helpers())
    helpers.update(_path_helpers())
    helpers.update(_encoding_helpers())
    helpers.update(_hash_helpers())
    helpers.update(_random_helpers())
    helpers.update(_network_helpers())
    helpers.update(_datetime_helpers())
    helpers.update(_json_helpers())
    helpers.update(_regex_helpers())
    helpers.update(_type_filter_helpers())
    helpers.update(_asm_helpers())
    helpers["is_windows"] = IS_WINDOWS
    helpers["platform"] = "windows" if IS_WINDOWS else "unix"
    helpers["export_typed_outputs"] = export_typed_outputs
    return helpers
