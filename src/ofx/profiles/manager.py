"""Profile manager — CRUD for ~/.ofx/profiles.yml.

Follows the same pattern as :class:`ofx.cloud.config.CloudProfileManager`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ofx.profiles.models import OFXProfile
from ofx.settings import BASE_DATA_DIR
from ofx.utils.config_store import load_yaml_dict, save_yaml_dict

logger = logging.getLogger("ofx")

PROFILES_FILE = BASE_DATA_DIR / "profiles.yml"


class ProfileManager:
    """Manages execution profiles stored in ``~/.ofx/profiles.yml``.

    File format::

        profiles:
          stealth:
            description: "Slow & quiet"
            rate_limit: 30
            delay: 2.0
            jitter: 1.0
            threads: 2
            time_window:
              enabled: true
              start: "09:00"
              end: "17:00"
              days: [monday, tuesday, wednesday, thursday, friday]
              timezone: US/Eastern
              warn_before_minutes: 15

          aggressive:
            rate_limit: 0
            threads: 50

        defaults:
          profile: stealth
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or PROFILES_FILE
        self._data: dict[str, Any] = {}
        self._load()

    # ── I/O ────────────────────────────────────────────────────────

    def _load(self) -> None:
        self._data = load_yaml_dict(self._path, warn_prefix="Failed to load profiles")

    def _save(self) -> None:
        save_yaml_dict(self._path, self._data)

    # ── Properties ─────────────────────────────────────────────────

    @property
    def profiles(self) -> dict[str, dict[str, Any]]:
        return self._data.get("profiles", {})

    @property
    def default_profile_name(self) -> str:
        return self._data.get("defaults", {}).get("profile", "")

    # ── Public API ─────────────────────────────────────────────────

    def list_profiles(self) -> list[str]:
        """Return sorted list of profile names."""
        return sorted(self.profiles.keys())

    def exists(self, name: str) -> bool:
        return name in self.profiles

    def get_profile_data(self, name: str) -> dict[str, Any]:
        """Get raw profile dict by name.

        Raises:
            KeyError: If the profile doesn't exist.
        """
        profiles = self.profiles
        if name not in profiles:
            available = ", ".join(sorted(profiles.keys())) or "(none)"
            raise KeyError(f"Profile '{name}' not found. Available: {available}")
        return dict(profiles[name])

    def resolve(self, name: str) -> OFXProfile:
        """Load a profile by name as a validated ``OFXProfile``."""
        data = self.get_profile_data(name)
        data.setdefault("name", name)
        return OFXProfile(**data)

    def resolve_or_default(self, name: str | None) -> OFXProfile | None:
        """Resolve profile by name, fallback to default, or return None."""
        target = name or self.default_profile_name
        if not target:
            return None
        try:
            return self.resolve(target)
        except KeyError:
            if name:
                logger.warning("Profile '%s' not found, running without profile", name)
            return None

    def add(self, name: str, profile_data: dict[str, Any]) -> None:
        """Create or update a profile."""
        if "profiles" not in self._data:
            self._data["profiles"] = {}
        self._data["profiles"][name] = profile_data
        self._save()
        logger.info("Profile '%s' saved", name)

    def remove(self, name: str) -> None:
        """Remove a profile.

        Raises:
            KeyError: If the profile doesn't exist.
        """
        profiles = self._data.get("profiles", {})
        if name not in profiles:
            raise KeyError(f"Profile '{name}' not found")
        del profiles[name]
        # Clear default if it pointed to this profile
        defaults = self._data.get("defaults", {})
        if defaults.get("profile") == name:
            defaults.pop("profile", None)
        self._save()
        logger.info("Profile '%s' removed", name)

    def set_default(self, name: str) -> None:
        """Set the default profile.

        Raises:
            KeyError: If the profile doesn't exist.
        """
        if name not in self.profiles:
            raise KeyError(f"Profile '{name}' not found")
        if "defaults" not in self._data:
            self._data["defaults"] = {}
        self._data["defaults"]["profile"] = name
        self._save()
        logger.info("Default profile set to '%s'", name)

    def add_from_model(self, profile: OFXProfile) -> None:
        """Save a profile from an ``OFXProfile`` model."""
        data = profile.model_dump(exclude_defaults=True)
        name = data.pop("name", "") or "unnamed"
        self.add(name, data)


# ── Module singleton ───────────────────────────────────────────────

_manager: ProfileManager | None = None


def get_profile_manager() -> ProfileManager:
    """Return (or create) the global :class:`ProfileManager`."""
    global _manager
    if _manager is None:
        _manager = ProfileManager()
    return _manager
