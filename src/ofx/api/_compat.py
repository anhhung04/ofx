"""Standalone shims for ofx.api modules so they run without ofx.settings."""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import secrets as _secrets
import sys
import tempfile
from pathlib import Path
from types import ModuleType

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

APP_BRANDING = "ofx"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the ``ofx`` namespace."""
    return logging.getLogger(name or APP_BRANDING)


# ---------------------------------------------------------------------------
# Path constants (mirrors ofx.settings but stdlib-only)
# ---------------------------------------------------------------------------

_TMP_BASE = Path(tempfile.mkdtemp(prefix=f".{_secrets.token_hex(4)}_"))
BASE_DATA_DIR: Path = _TMP_BASE / ".r"
TEMP_DIR: Path = Path(tempfile.gettempdir())
CONFIG_FILE: Path = BASE_DATA_DIR / "config.ini"
USER_EXPLOITS_DIR: Path = BASE_DATA_DIR / "exploits"
USER_SHELLCODE_CONNECTORS_DIR: Path = BASE_DATA_DIR / "shellcode" / "connectors"
USER_WEBSHELL_CONNECTORS_DIR: Path = BASE_DATA_DIR / "webshell" / "connectors"

# ---------------------------------------------------------------------------
# Exception classes (mirrors ofx.exceptions)
# ---------------------------------------------------------------------------


class BaseError(Exception):
    """Base exception."""


class APIError(BaseError):
    """Raised when API operations fail."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: str | None = None,
    ):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class OFXTimeoutError(BaseError):
    """Raised when operation times out."""

    def __init__(self, message: str, timeout_seconds: int | None = None):
        self.timeout_seconds = timeout_seconds
        super().__init__(message)


# ---------------------------------------------------------------------------
# Module loader helpers (mirrors ofx.utils.module_loader)
# ---------------------------------------------------------------------------


def module_name_for_path(prefix: str, path: Path) -> str:
    """Build a stable, unique module name for a file path."""
    digest = hashlib.sha1(path.as_posix().encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"{prefix}.{path.stem}_{digest}"


def load_module_from_file(path: Path, module_prefix: str) -> ModuleType | None:
    """Load a module from a file path under a unique module namespace."""
    module_name = module_name_for_path(module_prefix, path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def iter_subclasses(module: ModuleType, base_class: type) -> list[type]:
    """Return subclasses of *base_class* defined in *module*."""
    return [
        attr
        for attr in module.__dict__.values()
        if isinstance(attr, type)
        and issubclass(attr, base_class)
        and attr is not base_class
    ]
