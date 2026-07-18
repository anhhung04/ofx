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
from ofx.utils.config_store import load_yaml_dict, save_yaml_dict

logger = logging.getLogger("ofx")

CLOUD_CONFIG_FILE = BASE_DATA_DIR / "cloud.yml"

def _default_cloud_config_data() -> dict[str, Any]:
    """Starter cloud config created on first user use."""
    return {
        "profiles": {},
        "defaults": {"profile": ""},
    }

_CLOUD_CONFIG_FILE_HEADER = """# OFX cloud profiles

"""

def _dump_default_cloud_config_file() -> str:
    return _CLOUD_CONFIG_FILE_HEADER + yaml.dump(
        _default_cloud_config_data(),
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

class CloudProfileManager:
    """Manages cloud profiles stored in ~/.ofx/cloud.yml.

    Usage:
        manager = CloudProfileManager()
        config = manager.resolve("do-small")
        manager.add("new-profile", {...})
        manager.list_profiles()
    """

    def __init__(self, config_path: Path | None = None):
        self._path = config_path or CLOUD_CONFIG_FILE
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load cloud config from YAML file."""
        self._bootstrap_defaults()
        self._data = load_yaml_dict(
            self._path, warn_prefix="Failed to load cloud config"
        )

    def _save(self) -> None:
        """Save cloud config to YAML file."""
        save_yaml_dict(self._path, self._data)

    def _bootstrap_defaults(self) -> None:
        """Create a starter cloud.yml on first use in the default OFX path."""
        if self._path != CLOUD_CONFIG_FILE or self._path.exists():
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(_dump_default_cloud_config_file())

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

    def _resolve_profile_name(self, cloud_config: CloudConfig) -> str:
        profile_name = cloud_config.profile
        if profile_name:
            return profile_name
        if cloud_config.provider:
            return ""
        return self.default_profile_name

    @staticmethod
    def _default_profile_config(profile_name: str) -> CloudConfig:
        return CloudConfig.model_validate({"profile": profile_name}, strict=False)

    @classmethod
    def _config_overrides(
        cls,
        cloud_config: CloudConfig,
        *,
        profile_name: str,
    ) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        default_config = cls._default_profile_config(profile_name)
        for field_name in CloudConfig.model_fields:
            if field_name == "profile":
                continue
            current_value = getattr(cloud_config, field_name)
            default_value = getattr(default_config, field_name)
            if current_value != default_value:
                overrides[field_name] = current_value
        return overrides

    def _resolve_profile_base_data(self, profile_name: str) -> dict[str, Any] | None:
        try:
            return self.get_profile_data(profile_name)
        except KeyError:
            logger.warning(
                f"Cloud profile '{profile_name}' not found, using config as-is"
            )
            return None

    @classmethod
    def _merged_profile_config(
        cls,
        base_data: dict[str, Any],
        overrides: dict[str, Any],
    ) -> CloudConfig:
        merged = {**base_data, **overrides}
        merged.pop("profile", None)
        return CloudConfig(**merged)

    def resolve(self, cloud_config: CloudConfig) -> CloudConfig:
        """Resolve a CloudConfig by merging profile defaults with overrides.

        If the CloudConfig has a `profile` reference, loads that profile
        as the base and applies any inline overrides on top.

        Args:
            cloud_config: CloudConfig that may reference a profile.

        Returns:
            Fully resolved CloudConfig with profile + overrides merged.
        """
        profile_name = self._resolve_profile_name(cloud_config)
        if not profile_name:
            return cloud_config

        base_data = self._resolve_profile_base_data(profile_name)
        if base_data is None:
            return cloud_config

        overrides = self._config_overrides(cloud_config, profile_name=profile_name)
        return self._merged_profile_config(base_data, overrides)

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

_manager: CloudProfileManager | None = None

def get_cloud_profile_manager() -> CloudProfileManager:
    """Get the global cloud profile manager (lazy singleton)."""
    global _manager
    if _manager is None:
        _manager = CloudProfileManager()
    return _manager
