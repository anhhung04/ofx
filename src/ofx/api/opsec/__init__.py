"""OPSEC helpers for infrastructure privacy and traffic anonymisation.

Submodules
----------
cleanup  -- artefact removal, timestomping, secure deletion
proxy    -- proxychains config and proxy env vars
timing   -- business-hours check and random sleep
traffic  -- User-Agent rotation, header blending, domain fronting
"""

from __future__ import annotations

from .cleanup import (
    clean_history_commands,
    clean_linux_logs,
    clean_windows_artifacts,
    remove_ssh_known_host,
    secure_delete_command,
    timestomp_command,
)
from .proxy import build_proxychains_conf, http_proxy_env
from .timing import is_business_hours, random_sleep_seconds
from .traffic import (
    cdncheck_command,
    domain_fronting_headers,
    rotate_user_agent,
    traffic_blend_headers,
)

__all__ = [
    "clean_history_commands",
    "clean_linux_logs",
    "clean_windows_artifacts",
    "timestomp_command",
    "remove_ssh_known_host",
    "secure_delete_command",
    "build_proxychains_conf",
    "http_proxy_env",
    "is_business_hours",
    "random_sleep_seconds",
    "rotate_user_agent",
    "traffic_blend_headers",
    "domain_fronting_headers",
    "cdncheck_command",
]
