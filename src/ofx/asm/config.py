"""ASM connection configuration manager.

Stores ASM server URL and API token in ``~/.ofx/asm.yml``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ofx.settings import BASE_DATA_DIR, settings

logger = logging.getLogger(settings.app_branding)

ASM_CONFIG_PATH = BASE_DATA_DIR / "asm.yml"


class ASMConfig:
    """Manages ASM connection settings persisted to ``~/.ofx/asm.yml``."""

    def __init__(self, path: Path | None = None):
        self.path = path or ASM_CONFIG_PATH
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path) as fh:
                self._data = yaml.safe_load(fh) or {}
        else:
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as fh:
            yaml.safe_dump(self._data, fh, default_flow_style=False)

    @property
    def url(self) -> str:
        """Base URL for the ASM server (e.g. ``http://localhost:8080``)."""
        return self._data.get("url", "")

    @url.setter
    def url(self, value: str) -> None:
        self._data["url"] = value.rstrip("/")
        self._save()

    @property
    def token(self) -> str:
        """API token (Bearer) for authentication."""
        return self._data.get("token", "")

    @token.setter
    def token(self, value: str) -> None:
        self._data["token"] = value
        self._save()

    @property
    def default_scope(self) -> str:
        """Default scope ID used when none is specified on the CLI."""
        return self._data.get("default_scope", "")

    @default_scope.setter
    def default_scope(self, value: str) -> None:
        self._data["default_scope"] = value
        self._save()

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self._save()

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


_asm_config: ASMConfig | None = None


def get_asm_config() -> ASMConfig:
    """Return the singleton ``ASMConfig`` instance."""
    global _asm_config
    if _asm_config is None:
        _asm_config = ASMConfig()
    return _asm_config


def get_asm_client():
    """Return an ``ASMClient`` configured from ``~/.ofx/asm.yml``."""
    from ofx.asm.client import ASMClient

    cfg = get_asm_config()
    if not cfg.configured:
        raise RuntimeError(
            "ASM not configured. Run: ofx asm config set --url <URL> --token <TOKEN>"
        )
    return ASMClient(base_url=cfg.url, api_token=cfg.token)
