"""Template helper function factories.

Each factory returns a ``dict[str, Any]`` of named helpers that are
injected into the Jinja2 template environment.  Grouping by domain
makes the helpers independently testable and keeps ``get_support_functions()``
in *resolver.py* short.
"""

from __future__ import annotations

import base64
from functools import partial
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

def _field_value(item: Any, field: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)

def _as_list(items: Any) -> list | None:
    return items if isinstance(items, list) else None

def _slice_list(items: Any, n: int = 1, *, from_end: bool = False) -> list | Any:
    items_list = _as_list(items)
    if items_list is None:
        return [] if n > 1 else None
    if n == 1:
        if not items_list:
            return None
        return items_list[-1] if from_end else items_list[0]
    return items_list[-n:] if from_end else items_list[:n]

def _group_list(items: Any, field: str) -> dict[str, list]:
    items_list = _as_list(items)
    if items_list is None:
        return {}
    groups: dict[str, list] = {}
    for item in items_list:
        key = str(_field_value(item, field, ""))
        groups.setdefault(key, []).append(item)
    return groups

def _file_helpers() -> dict[str, Any]:
    def _read_file(path: str) -> str:
        file_path = path if isinstance(path, Path) else Path(path)
        if not file_path.exists() or not file_path.is_file():
            return ""
        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _logger.debug("file_read(%s) failed: %s", path, exc)
            return ""

    def _write_file(path: str, content: str) -> None:
        file_path = path if isinstance(path, Path) else Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def _append_file(path: str, content: str) -> None:
        file_path = path if isinstance(path, Path) else Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("a", encoding="utf-8") as f:
            f.write(content)

    def _file_lines(path: str) -> list[str]:
        file_path = path if isinstance(path, Path) else Path(path)
        if not file_path.exists() or not file_path.is_file():
            return []
        try:
            return file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            _logger.debug("file_lines(%s) failed: %s", path, exc)
            return []

    return {
        "file_read": _read_file,
        "file_write": _write_file,
        "file_append": _append_file,
        "file_lines": _file_lines,
        "file_exists": lambda path: (path if isinstance(path, Path) else Path(path)).exists(),
        "is_file": lambda path: (path if isinstance(path, Path) else Path(path)).is_file(),
        "is_dir": lambda path: (path if isinstance(path, Path) else Path(path)).is_dir(),
    }

def _path_helpers() -> dict[str, Any]:
    return {
        "join_path": lambda *parts: str(Path(*parts)),
        "basename": lambda path: (path if isinstance(path, Path) else Path(path)).name,
        "dirname": lambda path: str((path if isinstance(path, Path) else Path(path)).parent),
        "glob": lambda pattern, directory=".": [
            str(p) for p in (directory if isinstance(directory, Path) else Path(directory)).glob(pattern)
        ],
        "cwd": lambda: str(Path.cwd()),
        "home": lambda: str(Path.home()),
    }

def _encoding_helpers() -> dict[str, Any]:
    return {
        "b64encode": lambda s: base64.b64encode(s.encode()).decode(),
        "b64decode": lambda s: base64.b64decode(s.encode()).decode(),
        "url_encode": lambda s: quote(s, safe=""),
        "url_decode": lambda s: unquote(s),
        "hex_encode": lambda s: s.encode().hex(),
        "hex_decode": lambda s: bytes.fromhex(s).decode(),
    }

def _hash_helpers() -> dict[str, Any]:
    return {
        "md5": lambda s: hashlib.new("md5", s.encode()).hexdigest(),
        "sha1": lambda s: hashlib.new("sha1", s.encode()).hexdigest(),
        "sha256": lambda s: hashlib.new("sha256", s.encode()).hexdigest(),
    }

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

def _network_helpers() -> dict[str, Any]:
    def _get_local_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            _logger.debug("local_ip() socket probe failed", exc_info=True)
            return "127.0.0.1"

    def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                return sock.connect_ex((host, port)) == 0
        except (OSError, OverflowError, ValueError):
            _logger.debug("is_port_open(%s, %s) failed", host, port, exc_info=True)
            return False

    def _cidr_size(target: str) -> int:
        """Return the number of host addresses in a CIDR range.

        Accepts plain IPs (→ 1), CIDRs (``/24`` → 254), and
        comma-separated or space-separated lists of targets.
        """
        import ipaddress

        total = 0
        for part in re.split(r"[,\s]+", target.strip()):
            part = part.strip()
            if not part:
                continue
            try:
                net = ipaddress.ip_network(part, strict=False)
                total += max(net.num_addresses - 2, 1)
            except ValueError:
                total += 1
        return total

    return {
        "local_ip": _get_local_ip,
        "is_port_open": _is_port_open,
        "cidr_size": _cidr_size,
    }

def _datetime_helpers() -> dict[str, Any]:
    return {
        "now": lambda fmt="%Y-%m-%d %H:%M:%S": datetime.now().strftime(fmt),
        "timestamp": lambda: int(datetime.now().timestamp()),
    }

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

def _regex_helpers() -> dict[str, Any]:
    return {
        "regex_match": lambda pattern, s: bool(re.match(pattern, s)),
        "regex_search": lambda pattern, s: bool(re.search(pattern, s)),
        "regex_findall": lambda pattern, s: re.findall(pattern, s),
        "regex_sub": lambda pattern, repl, s: re.sub(pattern, repl, s),
    }

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

def _pluck_field(items: list, field: str) -> list:
    items_list = _as_list(items)
    if items_list is None:
        return []
    return [_field_value(item, field) for item in items_list]

def _join_lines(items: list, field: str | None = None, sep: str = "\n") -> str:
    items_list = _as_list(items)
    if items_list is None:
        return ""

    parts: list[str] = []
    for item in items_list:
        if field and isinstance(item, dict):
            parts.append(str(item.get(field, "")))
        else:
            parts.append(str(item))
    return sep.join(parts)

def _to_csv_string(items: list, headers: bool = True) -> str:
    import csv as _csv
    import io as _io

    if not items or not isinstance(items, list):
        return ""

    buf = _io.StringIO()
    if isinstance(items[0], dict):
        fieldnames = list(items[0].keys())
        writer = _csv.DictWriter(buf, fieldnames=fieldnames)
        if headers:
            writer.writeheader()
        for item in items:
            writer.writerow({key: str(value) for key, value in item.items()})
    return buf.getvalue().rstrip("\r\n")

def _to_jsonl_string(items: list) -> str:
    items_list = _as_list(items)
    if items_list is None:
        return ""
    return "\n".join(json.dumps(item, default=str) for item in items_list)

def _sort_items(items: list, field: str, reverse: bool = False) -> list:
    items_list = _as_list(items)
    if items_list is None:
        return []

    def _key(item: Any) -> tuple[int, int | float, str]:
        value = _field_value(item, field)
        if value is None:
            return (0, 0, "")
        if isinstance(value, (int, float)):
            return (0, value, "")
        try:
            return (0, float(value), "")
        except (ValueError, TypeError):
            return (1, 0, str(value))

    try:
        return sorted(items_list, key=_key, reverse=reverse)
    except TypeError:
        return items_list

def _unique_items(items: list, field: str) -> list:
    items_list = _as_list(items)
    if items_list is None:
        return []

    seen: set[Any] = set()
    result: list = []
    for item in items_list:
        key = _field_value(item, field)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result

def _filter_where(items: list, field: str, value: Any, *, negate: bool = False) -> list:
    items_list = _as_list(items)
    if items_list is None:
        return []
    result: list = []
    for item in items_list:
        matches = _field_value(item, field) == value
        if (not matches) if negate else matches:
            result.append(item)
    return result

def _flatten_items(items: list, field: str | None = None) -> list:
    items_list = _as_list(items)
    if items_list is None:
        return []
    if field:
        result: list = []
        for item in items_list:
            nested = _field_value(item, field)
            if isinstance(nested, list):
                result.extend(nested)
            else:
                result.append(item)
        return result

    result: list = []
    for item in items_list:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result

def _of_type(items: list, type_name: str) -> list:
    items_list = _as_list(items)
    if items_list is None:
        return []
    return [
        item
        for item in items_list
        if isinstance(item, dict) and item.get("_type") == type_name
    ]

def _type_filter_helpers() -> dict[str, Any]:
    return {
        "of_type": _of_type,
        **{
            name: partial(_of_type, type_name=type_name)
            for name, type_name in _TYPE_FILTER_MAP.items()
        },
    }

def _etl_helpers() -> dict[str, Any]:
    """Helpers for data transformation in templates.

    These complement ``pipe:`` steps by enabling lightweight inline
    transformations via Jinja2 filters and functions.
    """

    return {
        "pluck": _pluck_field,
        "to_lines": _join_lines,
        "to_csv": _to_csv_string,
        "to_jsonl": _to_jsonl_string,
        "sort_by": _sort_items,
        "unique_by": _unique_items,
        "where": _filter_where,
        "where_not": partial(_filter_where, negate=True),
        "first": _slice_list,
        "last": partial(_slice_list, from_end=True),
        "group_by": _group_list,
        "flatten": _flatten_items,
        "count_by": lambda items, field: {
            key: len(group) for key, group in _group_list(items, field).items()
        },
    }

_HELPER_GROUP_FACTORIES = (
    _file_helpers,
    _path_helpers,
    _encoding_helpers,
    _hash_helpers,
    _random_helpers,
    _network_helpers,
    _datetime_helpers,
    _json_helpers,
    _regex_helpers,
    _type_filter_helpers,
    _etl_helpers,
)

def build_all_helpers() -> dict[str, Any]:
    """Aggregate every helper group into a single dict.

    Called by :pymethod:`TemplateResolver.get_support_functions` and also
    usable in tests for direct validation.
    """
    from ofx.runner.commands.shell_functions import get_shell_exports
    from ofx.runner.findings_export import export_typed_outputs
    from ofx.settings import IS_WINDOWS

    helpers: dict[str, Any] = dict(get_shell_exports())
    for factory in _HELPER_GROUP_FACTORIES:
        helpers.update(factory())
    helpers["is_windows"] = IS_WINDOWS
    helpers["platform"] = "windows" if IS_WINDOWS else "unix"
    helpers["export_typed_outputs"] = export_typed_outputs
    return helpers
