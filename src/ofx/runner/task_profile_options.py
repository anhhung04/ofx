"""Shared profile option merging helpers for task execution."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
import shlex
from typing import Any
from urllib.parse import urlparse

COMMON_TASK_PROFILE_MAPPING: list[tuple[str, list[str]]] = [
    ("proxy", ["proxy", "proxy_url", "http_proxy"]),
    ("threads", ["threads", "concurrency", "workers"]),
    ("rate_limit", ["rate_limit", "rate"]),
    ("delay", ["delay"]),
    ("user_agent", ["user_agent"]),
    ("jitter", ["jitter"]),
]

_PROFILE_ENV_SPECS: tuple[tuple[str, str, object | None], ...] = (
    ("OFX_RATE_LIMIT", "rate_limit", None),
    ("OFX_THREADS", "threads", 10),
    ("OFX_TIMEOUT", "timeout_minutes", 60),
    ("OFX_DELAY", "delay", None),
    ("OFX_JITTER", "jitter", None),
    ("OFX_PROXY", "proxy", None),
    ("OFX_USER_AGENT", "user_agent", None),
)

_PROFILE_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "rate_limit",
    "max_retries",
    "timeout_minutes",
    "threads",
    "retry_policy",
    "retry_profiles",
    "delay",
    "jitter",
    "user_agent",
    "proxy",
    "time_window",
    "env",
    "tags",
    "task_options",
)

_ENV_KEY_SANITIZE_RE = re.compile(r"[^A-Z0-9_]+")


def merge_profile_task_options(
    *,
    task_name: str,
    user_opts: Mapping[str, Any],
    task_declared_opts: Mapping[str, Any] | None,
    profile: Any,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Merge common profile settings and per-task overrides.

    Returns `(merged_opts, injected_common_opts, override_keys)`.
    User-provided options always win over profile-provided values.
    """

    merged = dict(user_opts)
    declared = task_declared_opts or {}
    injected: list[str] = []
    for profile_attr, candidate_names in COMMON_TASK_PROFILE_MAPPING:
        value = getattr(profile, profile_attr, None)
        if value is None:
            continue
        if isinstance(value, (int, float)) and value == 0:
            continue
        if isinstance(value, str) and not value:
            continue

        opt_name = next(
            (
                candidate_name
                for candidate_name in candidate_names
                if candidate_name in declared and candidate_name not in merged
            ),
            None,
        )
        if opt_name is None:
            continue
        merged[opt_name] = value
        injected.append(f"{opt_name}={value}")

    task_options = getattr(profile, "task_options", None) or {}
    overrides = dict(task_options.get(task_name, {}) or {})
    override_keys = list(overrides.keys()) if overrides else []
    if overrides:
        overrides.update(merged)
        merged = overrides

    return merged, injected, override_keys


def build_profile_env_overrides(profile: Any | None) -> dict[str, str]:
    """Build environment variables implied by a profile.

    Includes the existing ``OFX_*`` metadata envs and, when ``proxy`` is set,
    standard proxy env vars for tools that honor them.
    """
    if profile is None:
        return {}

    profile_data = profile_to_dict(profile)
    env: dict[str, str] = {}
    for env_key, profile_attr, default_value in _PROFILE_ENV_SPECS:
        value = getattr(profile, profile_attr, None)
        if bool(value) if default_value is None else value != default_value:
            env[env_key] = str(value)

    for key, value in profile_data.items():
        if value in (None, "", [], {}):
            continue
        env[_profile_field_env_key(key)] = _serialize_profile_env_value(value)

    if profile_data:
        env["OFX_PROFILE_JSON"] = json.dumps(profile_data, sort_keys=True, default=str)

    proxy = getattr(profile, "proxy", "") or ""
    if proxy:
        env.update(_build_proxy_env_overrides(proxy))

    env.update({key: str(value) for key, value in (getattr(profile, "env", None) or {}).items()})
    return env


def build_profile_var_overrides(profile: Any | None) -> dict[str, Any]:
    """Build shared profile vars injected into runner contexts."""
    if profile is None:
        return {}

    return {
        "profile": profile_to_dict(profile),
        "profile_model": profile,
    }


def profile_to_dict(profile: Any | None) -> dict[str, Any]:
    """Normalize profile-like objects to a serializable dict."""
    if profile is None:
        return {}

    data: dict[str, Any] = {}
    if hasattr(profile, "model_dump"):
        data.update(dict(profile.model_dump()))

    for field in _PROFILE_TOP_LEVEL_FIELDS:
        if not hasattr(profile, field):
            continue
        value = getattr(profile, field)
        if hasattr(value, "model_dump"):
            data[field] = value.model_dump()
        else:
            data[field] = value
    return data


def adapt_task_command_for_profile(
    command: str,
    *,
    task_declared_opts: Mapping[str, Any] | None,
    resolved_opts: Mapping[str, Any],
    profile: Any | None,
) -> str:
    """Apply profile-level command adaptation after a task command is built.

    Native task opts remain the first choice. The shell-level fallback is only
    used for profile fields that still need to affect the final process.
    """
    if not command or profile is None:
        return command

    env_overrides = {
        key: str(value) for key, value in (getattr(profile, "env", None) or {}).items()
    }
    if not _task_uses_native_proxy(task_declared_opts, resolved_opts):
        env_overrides.update(
            _build_proxy_env_overrides(getattr(profile, "proxy", "") or "")
        )

    if not env_overrides:
        return command

    assignments = " ".join(
        shlex.quote(f"{key}={value}") for key, value in env_overrides.items()
    )
    return f"env {assignments} {command}"


def _task_uses_native_proxy(
    task_declared_opts: Mapping[str, Any] | None,
    resolved_opts: Mapping[str, Any],
) -> bool:
    declared = task_declared_opts or {}
    proxy_opt_names = next(
        candidates
        for profile_attr, candidates in COMMON_TASK_PROFILE_MAPPING
        if profile_attr == "proxy"
    )
    return any(
        opt_name in declared and resolved_opts.get(opt_name)
        for opt_name in proxy_opt_names
    )


def _build_proxy_env_overrides(proxy_url: str) -> dict[str, str]:
    if not proxy_url:
        return {}

    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        return {}

    return {
        "http_proxy": proxy_url,
        "https_proxy": proxy_url,
        "HTTP_PROXY": proxy_url,
        "HTTPS_PROXY": proxy_url,
        "ALL_PROXY": proxy_url,
    }


def _profile_field_env_key(field_name: str) -> str:
    normalized = _ENV_KEY_SANITIZE_RE.sub("_", field_name.upper()).strip("_")
    return f"OFX_PROFILE_{normalized}"


def _serialize_profile_env_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


__all__ = [
    "COMMON_TASK_PROFILE_MAPPING",
    "adapt_task_command_for_profile",
    "build_profile_env_overrides",
    "build_profile_var_overrides",
    "merge_profile_task_options",
    "profile_to_dict",
]
