import os
import tempfile
from pathlib import Path
from pydantic_settings_yaml import YamlBaseSettings
from pydantic_settings import SettingsConfigDict

from pydantic import Field

BASE_CONFIG_DIR = Path.home() / ".config" / "ofx"
BASE_DATA_DIR = Path.home() / ".local" / "share" / "ofx"
TEMP_DIR = Path(tempfile.gettempdir()) / ".ofx"
SECRETS_DIR = BASE_CONFIG_DIR / "secrets"

CONFIG_FILE = BASE_CONFIG_DIR / "config.yml"

os.makedirs(BASE_CONFIG_DIR, exist_ok=True)
os.makedirs(BASE_DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(SECRETS_DIR, exist_ok=True)


class Settings(YamlBaseSettings):
    """
    Application settings for OFX.
    """

    app_name: str = "Offensive Flow Executor"
    app_version: str = "0.1.0"
    app_branding: str = "ofx"
    debug: bool = Field(default=False, description="Enable debug mode")

    model_config = SettingsConfigDict(
        yaml_file=CONFIG_FILE.absolute(),
        secrets_dir=os.getenv("OFX_SECRETS", SECRETS_DIR.absolute()),
        env_prefix=f"{app_branding.upper()}_",
        env_file=".env",
    )


def create_settings():
    """
    Create and return the settings instance.
    """
    DEFAULT_CONFIG_CONTENT = """
debug: false
    """
    # check if the config file exists, if not create it
    if not CONFIG_FILE.exists():
        CONFIG_FILE.touch()
        with CONFIG_FILE.open("w") as f:
            f.write(DEFAULT_CONFIG_CONTENT.strip())
    return Settings()


settings = create_settings()
