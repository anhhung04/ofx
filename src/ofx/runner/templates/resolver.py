"""Template resolver for Jinja2-based workflow templates"""

import json
import threading
from pathlib import Path
from typing import Any

from jinja2 import Environment
from pydantic import BaseModel

from ofx.runner.core.registry_keys import RunnerRegistryKeys

_resolver_lock = threading.Lock()


def _tojson_python(value: Any, indent: int | None = None) -> str:
    """JSON serialization that outputs Python-compatible literals.

    Replaces JSON ``true``/``false``/``null`` with Python's
    ``True``/``False``/``None`` so the output can be used directly
    in inline ``script:`` blocks.
    """
    raw = json.dumps(value, indent=indent, default=str)
    # Replace JSON booleans/null with Python equivalents.
    # Only replace standalone tokens, not substrings inside strings.
    # json.dumps quotes string values, so bare true/false/null are safe to replace.
    raw = raw.replace(": true", ": True")
    raw = raw.replace(": false", ": False")
    raw = raw.replace(": null", ": None")
    raw = raw.replace("[true", "[True")
    raw = raw.replace("[false", "[False")
    raw = raw.replace("[null", "[None")
    raw = raw.replace(", true", ", True")
    raw = raw.replace(", false", ", False")
    raw = raw.replace(", null", ", None")
    return raw


def _build_jinja_env() -> Environment:
    """Create a Jinja2 Environment with Python-safe ``tojson`` filter."""
    env = Environment(enable_async=True)
    env.filters["tojson"] = _tojson_python
    return env


_jinja_env = _build_jinja_env()


class _StepAccessor(dict):
    """Dict that supports both name-based and integer-index access for steps."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            key = str(key)
        return super().__getitem__(key)


class TemplateResolver:
    """Handles template resolution with caching and optimization"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            with _resolver_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._template_cache = {}
                    inst._support_funcs_cache = None
                    inst._template_cache_max_size = 1000
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        # Initialization moved to __new__ to avoid resetting on repeated calls
        pass

    async def resolve(
        self,
        value: Any,
        context_vars: dict[str, Any],
        _memo: dict[str, Any] | None = None,
    ) -> Any:
        """Resolve Jinja2 templates in values recursively with optimized caching
        Args:
            value: Value to resolve (can be str, dict, list, primitives)
            context_vars: Context variables for template rendering
        Returns:
            Resolved value with templates expanded
        """
        memo = _memo or {}
        if value is None:
            return value
        elif isinstance(value, dict):
            return {
                k: await self.resolve(v, context_vars, memo) for k, v in value.items()
            }
        elif isinstance(value, list):
            return [await self.resolve(v, context_vars, memo) for v in value]
        elif issubclass(type(value), BaseModel):
            return value.model_copy(
                update={k: await self.resolve(v, context_vars, memo) for k, v in value}
            )
        elif not isinstance(value, (str, int, float, bool, dict, list)):
            return value

        value_str = str(value)
        if "{{" not in value_str and "{%" not in value_str:
            return value

        # Circular reference detection
        resolve_stack: list[str] = memo.setdefault("_resolve_stack", [])
        if value_str in resolve_stack:
            chain = " → ".join(resolve_stack + [value_str])
            raise ValueError(f"Circular template reference detected: {chain}")
        resolve_stack.append(value_str)

        support_funcs = await self._build_support_functions(context_vars, memo)

        if value_str not in self._template_cache:
            if len(self._template_cache) >= self._template_cache_max_size:
                first_key = next(iter(self._template_cache))
                del self._template_cache[first_key]
            self._template_cache[value_str] = _jinja_env.from_string(value_str)

        template = self._template_cache[value_str]

        template_vars = context_vars.copy()
        template_vars.update(support_funcs)

        try:
            result = await template.render_async(template_vars)
        except Exception as e:
            # Provide actionable context for template errors
            preview = value_str[:120] + ("…" if len(value_str) > 120 else "")
            raise type(e)(
                f"Template rendering failed: {e}\n"
                f"  Template: {preview}"
            ) from e

        resolve_stack.pop()

        if isinstance(value, bool):
            return result.lower() in ("true", "yes", "1", "t", "y")
        elif isinstance(value, int):
            try:
                return int(result)
            except ValueError:
                return result
        elif isinstance(value, float):
            try:
                return float(result)
            except ValueError:
                return result

        return result

    def get_support_functions(self) -> dict[str, Any]:
        """Get template support functions with caching"""
        import base64
        import hashlib
        import json
        import random
        import re
        import secrets
        import socket
        import string
        import uuid
        from datetime import datetime
        from urllib.parse import quote, unquote

        from ofx.runner.commands.shell_functions import get_shell_exports
        from ofx.settings import IS_WINDOWS

        # File utilities
        def _read_file(path: str) -> str:
            file_path = Path(path)
            if not file_path.exists():
                return ""
            return file_path.read_text()

        def _write_file(path: str, content: str) -> None:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        def _append_file(path: str, content: str) -> None:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open("a") as f:
                f.write(content)

        def _file_lines(path: str) -> list[str]:
            file_path = Path(path)
            if not file_path.exists():
                return []
            return file_path.read_text().splitlines()

        # String encoding utilities
        def _b64encode(s: str) -> str:
            return base64.b64encode(s.encode()).decode()

        def _b64decode(s: str) -> str:
            return base64.b64decode(s.encode()).decode()

        def _url_encode(s: str) -> str:
            return quote(s, safe="")

        def _url_decode(s: str) -> str:
            return unquote(s)

        def _hex_encode(s: str) -> str:
            return s.encode().hex()

        def _hex_decode(s: str) -> str:
            return bytes.fromhex(s).decode()

        # Hash functions
        def _md5(s: str) -> str:
            return hashlib.md5(s.encode()).hexdigest()

        def _sha1(s: str) -> str:
            return hashlib.sha1(s.encode()).hexdigest()

        def _sha256(s: str) -> str:
            return hashlib.sha256(s.encode()).hexdigest()

        # Random generators
        def _random_string(length: int = 8, charset: str = "alphanumeric") -> str:
            if charset == "alpha":
                chars = string.ascii_letters
            elif charset == "numeric":
                chars = string.digits
            elif charset == "hex":
                chars = string.hexdigits[:16]
            else:  # alphanumeric
                chars = string.ascii_letters + string.digits
            return "".join(random.choices(chars, k=length))

        def _random_int(min_val: int = 0, max_val: int = 100) -> int:
            return random.randint(min_val, max_val)

        def _random_port(start: int = 1024, end: int = 65535) -> int:
            return random.randint(start, end)

        # Network utilities
        def _get_local_ip() -> str:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "127.0.0.1"

        def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                result = s.connect_ex((host, port))
                s.close()
                return result == 0
            except Exception:
                return False

        # Date/time utilities
        def _now(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
            return datetime.now().strftime(fmt)

        def _timestamp() -> int:
            return int(datetime.now().timestamp())

        # JSON utilities
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

        # Path utilities
        def _join_path(*parts: str) -> str:
            return str(Path(*parts))

        def _basename(path: str) -> str:
            return Path(path).name

        def _dirname(path: str) -> str:
            return str(Path(path).parent)

        def _glob(pattern: str, directory: str = ".") -> list[str]:
            return [str(p) for p in Path(directory).glob(pattern)]

        # ── Task typed-output helpers ──────────────────────────────
        def _of_type(items: list, type_name: str) -> list:
            """Filter a list of typed_output dicts to those matching *type_name*."""
            if not isinstance(items, list):
                return []
            return [i for i in items if isinstance(i, dict) and i.get("_type") == type_name]

        def _ports(items: list) -> list:
            return _of_type(items, "port")

        def _urls(items: list) -> list:
            return _of_type(items, "url")

        def _vulns(items: list) -> list:
            return _of_type(items, "vulnerability")

        def _subdomains(items: list) -> list:
            return _of_type(items, "subdomain")

        def _ips(items: list) -> list:
            return _of_type(items, "ip")

        def _tags(items: list) -> list:
            return _of_type(items, "tag")

        def _records(items: list) -> list:
            return _of_type(items, "record")

        def _domains(items: list) -> list:
            return _of_type(items, "domain")

        def _users(items: list) -> list:
            return _of_type(items, "user_account")

        if self._support_funcs_cache is None:
            from ofx.runner.execution.findings_export import export_typed_outputs
            shell_exports = get_shell_exports()

            self._support_funcs_cache = {
                # Shell variables
                **shell_exports,
                # Platform info
                "is_windows": IS_WINDOWS,
                "platform": "windows" if IS_WINDOWS else "unix",
                # File utilities
                "file_read": _read_file,
                "file_write": _write_file,
                "file_append": _append_file,
                "file_lines": _file_lines,
                "file_exists": lambda path: Path(path).exists(),
                "is_file": lambda path: Path(path).is_file(),
                "is_dir": lambda path: Path(path).is_dir(),
                # Path utilities
                "join_path": _join_path,
                "basename": _basename,
                "dirname": _dirname,
                "glob": _glob,
                "cwd": lambda: str(Path.cwd()),
                "home": lambda: str(Path.home()),
                # String encoding
                "b64encode": _b64encode,
                "b64decode": _b64decode,
                "url_encode": _url_encode,
                "url_decode": _url_decode,
                "hex_encode": _hex_encode,
                "hex_decode": _hex_decode,
                # Hash functions
                "md5": _md5,
                "sha1": _sha1,
                "sha256": _sha256,
                # Random generators
                "random_string": _random_string,
                "random_int": _random_int,
                "random_port": _random_port,
                "uuid": lambda: str(uuid.uuid4()),
                "token": lambda n=32: secrets.token_urlsafe(n),
                # Network utilities
                "local_ip": _get_local_ip,
                "is_port_open": _is_port_open,
                # Date/time
                "now": _now,
                "timestamp": _timestamp,
                # JSON
                "to_json": _to_json,
                "from_json": _from_json,
                # Regex
                "regex_match": lambda pattern, s: bool(re.match(pattern, s)),
                "regex_search": lambda pattern, s: bool(re.search(pattern, s)),
                "regex_findall": lambda pattern, s: re.findall(pattern, s),
                "regex_sub": lambda pattern, repl, s: re.sub(pattern, repl, s),
                # Task output helpers
                "of_type": _of_type,
                "ports": _ports,
                "urls": _urls,
                "vulns": _vulns,
                "subdomains": _subdomains,
                "ips": _ips,
                "tags": _tags,
                "records": _records,
                "domains": _domains,
                "users": _users,
                "export_typed_outputs": export_typed_outputs,
            }

        support_funcs = self._support_funcs_cache.copy()

        return support_funcs

    async def _build_support_functions(
        self, context_vars: dict[str, Any], memo: dict[str, Any]
    ) -> dict[str, Any]:
        """Build support functions once per resolve call and reuse in recursion."""

        if "support_funcs" in memo:
            return memo["support_funcs"]

        support_funcs = self.get_support_functions()

        # Add registry-based data for accessing job and step data
        if "registry" in context_vars:
            registry = context_vars["registry"]
            jobs_data: dict[str, Any] = memo.get("jobs_data", {})
            steps_data: dict[str, Any] = memo.get("steps_data", {})

            runner = context_vars.get("runner")
            if runner is not None and not jobs_data and not steps_data:
                jobs_data = await self._jobs_from_runner(runner)
                steps_data = await self._steps_from_runner(runner)
                memo["jobs_data"] = jobs_data
                memo["steps_data"] = steps_data

            # Fallbacks for legacy registry usage
            if not jobs_data:
                jobs_data = await registry.get("jobs:results") or {}
                memo["jobs_data"] = jobs_data
            if not steps_data and "current_job_id" in context_vars:
                job_id = context_vars["current_job_id"]
                step_results = await registry.get(f"jobs:{job_id}:steps") or {}
                steps_data = dict(step_results)
                memo["steps_data"] = steps_data

            support_funcs["jobs"] = jobs_data
            support_funcs["steps"] = steps_data

        memo["support_funcs"] = support_funcs
        return support_funcs

    async def _jobs_from_runner(self, runner: Any) -> dict[str, Any]:
        container = self._find_container_with_child_attr(runner, "jid")
        if not container:
            return {}

        jobs: dict[str, Any] = {}
        for child in getattr(container, "_runners", {}).values():
            await self._collect_job_output(child, jobs)
        return jobs

    async def _collect_job_output(self, runner: Any, jobs: dict[str, Any]) -> None:
        model = getattr(runner, "model", None)
        if model is not None and hasattr(model, "jid"):
            job_id = getattr(model, "jid", None) or getattr(
                model, "original_job_id", ""
            )
            if job_id:
                outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
                jobs[job_id] = {"outputs": outputs}

        for child in getattr(runner, "_runners", {}).values():
            model = getattr(child, "model", None)
            if model is None or not hasattr(model, "jid"):
                continue
            job_id = getattr(model, "jid", None) or getattr(
                model, "original_job_id", ""
            )
            if not job_id:
                continue
            outputs = await child.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
            jobs[job_id] = {"outputs": outputs}

    async def _steps_from_runner(self, runner: Any) -> _StepAccessor:
        container = self._find_container_with_child_attr(runner, "step_index")
        if not container:
            return _StepAccessor()

        steps = _StepAccessor()
        for child in getattr(container, "_runners", {}).values():
            model = getattr(child, "model", None)
            if model is None or not hasattr(model, "step_index"):
                continue
            outputs = await child.reg_get(RunnerRegistryKeys.OUTPUTS) or {}
            entry = {
                "index": getattr(model, "step_index", None),
                "name": getattr(model, "name", None),
                "outputs": outputs,
            }
            name = getattr(model, "name", None)
            if name:
                steps[name] = entry
            # Also allow numeric index access
            idx = getattr(model, "step_index", None)
            if idx is not None:
                steps[str(idx)] = entry

        return steps

    def _find_container_with_child_attr(self, runner: Any, attr: str) -> Any | None:
        current = runner
        while current is not None:
            children = getattr(current, "_runners", None)
            if children:
                for child in children.values():
                    model = getattr(child, "model", None)
                    if model is not None and hasattr(model, attr):
                        return current
            current = getattr(current, "parent", None)
        return None

    def clear_cache(self):
        """Clear the template cache"""
        self._template_cache.clear()
        if self._support_funcs_cache:
            self._support_funcs_cache.clear()
