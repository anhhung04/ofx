"""Cloud profile configuration manager.

Loads and saves cloud profiles from ~/.ofx/cloud.yml.
Profiles are named cloud configurations that can be referenced
by slug in workflow YAML files.

File format (~/.ofx/cloud.yml):
    profiles:
      do-small:
        provider: digitalocean
        region: nyc3
        size: s-1vcpu-1gb
        image: ofx-base
        ssh_key: ~/.ssh/id_ed25519
        auto_destroy: true

      aws-large:
        provider: aws
        region: us-east-1
        size: t3.medium
        image: ami-0xxxx
        key_pair_name: ofx-key

    defaults:
      profile: do-small
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ofx.models.cloud import CloudConfig
from ofx.settings import BASE_DATA_DIR

logger = logging.getLogger("ofx")

CLOUD_CONFIG_FILE = BASE_DATA_DIR / "cloud.yml"


class CloudProfileManager:
    """Manages cloud profiles stored in ~/.ofx/cloud.yml.

    Usage:
        manager = CloudProfileManager()
        config = manager.resolve("do-small")  # Load profile by name
        manager.add("new-profile", {...})      # Add new profile
        manager.list_profiles()                # List all profiles
    """

    def __init__(self, config_path: Path | None = None):
        self._path = config_path or CLOUD_CONFIG_FILE
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load cloud config from YAML file."""
        if self._path.exists():
            try:
                text = self._path.read_text()
                self._data = yaml.safe_load(text) or {}
            except Exception as e:
                logger.warning(f"Failed to load cloud config from {self._path}: {e}")
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """Save cloud config to YAML file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            yaml.dump(self._data, default_flow_style=False, sort_keys=False)
        )

    @property
    def profiles(self) -> dict[str, dict[str, Any]]:
        """Get all profile definitions."""
        return self._data.get("profiles", {})

    @property
    def default_profile_name(self) -> str:
        """Get the default profile name."""
        defaults = self._data.get("defaults", {})
        return defaults.get("profile", "")

    def list_profiles(self) -> list[str]:
        """List all profile names."""
        return sorted(self.profiles.keys())

    def get_profile_data(self, name: str) -> dict[str, Any]:
        """Get raw profile data by name.

        Args:
            name: Profile name/slug.

        Returns:
            Profile data dict.

        Raises:
            KeyError: If profile not found.
        """
        profiles = self.profiles
        if name not in profiles:
            available = ", ".join(sorted(profiles.keys())) or "(none)"
            raise KeyError(f"Cloud profile '{name}' not found. Available: {available}")
        return dict(profiles[name])

    def resolve(self, cloud_config: CloudConfig) -> CloudConfig:
        """Resolve a CloudConfig by merging profile defaults with overrides.

        If the CloudConfig has a `profile` reference, loads that profile
        as the base and applies any inline overrides on top.

        Args:
            cloud_config: CloudConfig that may reference a profile.

        Returns:
            Fully resolved CloudConfig with profile + overrides merged.
        """
        profile_name = cloud_config.profile

        if not profile_name:
            # No profile reference — check if we should use the default
            if not cloud_config.provider:
                default = self.default_profile_name
                if default:
                    profile_name = default
                else:
                    return cloud_config

        if not profile_name:
            return cloud_config

        # Load base profile
        try:
            base_data = self.get_profile_data(profile_name)
        except KeyError:
            logger.warning(
                f"Cloud profile '{profile_name}' not found, using config as-is"
            )
            return cloud_config

        # Get overrides from the inline config (non-default values)
        overrides = {}
        default_config = CloudConfig.model_validate({"profile": profile_name}, strict=False)
        for field_name, _field_info in CloudConfig.model_fields.items():
            if field_name == "profile":
                continue
            current_value = getattr(cloud_config, field_name)
            default_value = getattr(default_config, field_name)
            if current_value != default_value:
                overrides[field_name] = current_value

        # Merge: profile base + inline overrides
        merged = {**base_data, **overrides}
        merged.pop("profile", None)  # Don't re-set profile

        return CloudConfig(**merged)

    def add(self, name: str, profile_data: dict[str, Any]) -> None:
        """Add or update a cloud profile.

        Args:
            name: Profile name/slug.
            profile_data: Profile configuration dict.
        """
        if "profiles" not in self._data:
            self._data["profiles"] = {}
        self._data["profiles"][name] = profile_data
        self._save()
        logger.info(f"Cloud profile '{name}' saved")

    def remove(self, name: str) -> None:
        """Remove a cloud profile.

        Args:
            name: Profile name to remove.

        Raises:
            KeyError: If profile not found.
        """
        profiles = self._data.get("profiles", {})
        if name not in profiles:
            raise KeyError(f"Cloud profile '{name}' not found")
        del profiles[name]
        self._save()
        logger.info(f"Cloud profile '{name}' removed")

    def set_default(self, name: str) -> None:
        """Set the default cloud profile.

        Args:
            name: Profile name to set as default.

        Raises:
            KeyError: If profile not found.
        """
        if name not in self.profiles:
            raise KeyError(f"Cloud profile '{name}' not found")
        if "defaults" not in self._data:
            self._data["defaults"] = {}
        self._data["defaults"]["profile"] = name
        self._save()
        logger.info(f"Default cloud profile set to '{name}'")

    def exists(self, name: str) -> bool:
        """Check if a profile exists."""
        return name in self.profiles

    def as_cloud_config(self, name: str) -> CloudConfig:
        """Load a profile as a CloudConfig object.

        Args:
            name: Profile name.

        Returns:
            CloudConfig populated from the profile.
        """
        data = self.get_profile_data(name)
        return CloudConfig(**data)


# Module-level singleton for convenience
_manager: CloudProfileManager | None = None


def get_cloud_profile_manager() -> CloudProfileManager:
    """Get the global cloud profile manager (lazy singleton)."""
    global _manager
    if _manager is None:
        _manager = CloudProfileManager()
    return _manager
