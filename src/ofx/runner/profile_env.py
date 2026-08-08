"""Profile environment variable helpers (minimal, post-task removal)."""

from __future__ import annotations

import json
import re
from typing import Any


_PROFILE_ENV_ATTRS: tuple[tuple[str, str, object | None], ...] = (
    ("OFX_RATE_LIMIT", "rate_limit", None),
    ("OFX_THREADS", "threads", 10),
    ("OFX_TIMEOUT", "timeout_minutes", 60),
    ("OFX_DELAY", "delay", None),
    ("OFX_JITTER", "jitter", None),
)


def build_profile_env_overrides(profile: Any | None) -> dict[str, str]:
    """Build environment variables implied by a profile."""
    if profile is None:
        return {}

    env: dict[str, str] = {}
    for env_key, profile_attr, default_value in _PROFILE_ENV_ATTRS:
        value = getattr(profile, profile_attr, None)
        if bool(value) if default_value is None else value != default_value:
            env[env_key] = str(value)

    proxy = getattr(profile, "proxy", "") or ""
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
        env["ALL_PROXY"] = proxy

    # Include custom env vars from the profile
    custom_env = getattr(profile, "env", None) or {}
    if isinstance(custom_env, dict):
        env.update({k: str(v) for k, v in custom_env.items() if v})

    # Serialize profile fields as OFX_PROFILE_* env vars
    profile_data = _profile_to_dict(profile)
    for key, value in profile_data.items():
        if value in (None, "", [], {}):
            continue
        env_key = _profile_field_env_key(key)
        env[env_key] = _serialize_profile_env_value(value)

    if profile_data:
        env["OFX_PROFILE_JSON"] = json.dumps(profile_data, sort_keys=True, default=str)

    return env


def _profile_field_env_key(field_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "_", field_name.upper()).strip("_")
    return f"OFX_PROFILE_{normalized}"


def _serialize_profile_env_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_profile_var_overrides(profile: Any | None) -> dict[str, Any]:
    """Build template variables from a profile."""
    if profile is None:
        return {}
    return {
        "profile": _profile_to_dict(profile),
        "profile_model": profile,
    }


def _profile_to_dict(profile: Any) -> dict[str, Any]:
    """Normalize profile-like objects to a serializable dict."""
    if hasattr(profile, "model_dump"):
        data = profile.model_dump()
    else:
        data = {}
    # Also include non-private, non-callable attributes
    for attr in dir(profile):
        if attr.startswith("_") or attr == "model_dump":
            continue
        try:
            value = getattr(profile, attr)
        except Exception:
            continue
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool, list, dict, type(None))):
            data[attr] = value
        elif hasattr(value, "model_dump"):
            data[attr] = value.model_dump()
        else:
            data[attr] = str(value)
    return data


__all__ = [
    "build_profile_env_overrides",
    "build_profile_var_overrides",
]