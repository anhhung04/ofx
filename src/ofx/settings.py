import os
import tempfile
from pathlib import Path
from pydantic_settings_yaml import YamlBaseSettings
from pydantic_settings import SettingsConfigDict

from ofx.utils.log import reload_logging_config

from pydantic import Field, BaseModel

BASE_CONFIG_DIR = Path.home() / ".config" / "ofx"
BASE_DATA_DIR = Path.home() / ".local" / "share" / "ofx"
TEMP_DIR = Path(tempfile.gettempdir()) / ".ofx"
SECRETS_DIR = BASE_CONFIG_DIR / "secrets"
DEFAULT_WORKFLOWS_DIR = BASE_DATA_DIR / "workflows"

CONFIG_FILE = BASE_CONFIG_DIR / "config.yml"

BANNER = """
\033[1;31m      .--.
     |o_o |
     |:_/ |
    //   \\ \\
   (|     | )
  /'\\_   _/`\\
  \\___)=(___/\033[0m

\033[1mOffensive Flow Executor\033[0m
> Handing over to the next generation of red teamers
"""

os.makedirs(BASE_CONFIG_DIR, exist_ok=True)
os.makedirs(BASE_DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(SECRETS_DIR, exist_ok=True)


class SecretConfig(BaseModel):
    pass


class Settings(YamlBaseSettings):
    """
    Application settings for OFX.
    """

    app_name: str = "Offensive Flow Executor"
    app_version: str = "0.1.0"
    app_branding: str = "ofx"
    model_config = SettingsConfigDict(
        yaml_file=CONFIG_FILE.absolute(),
        secrets_dir=SECRETS_DIR.absolute(),
        env_prefix=f"{app_branding.upper()}_",
        env_file=".env",
    )

    debug: bool = Field(default=False, description="Enable debug mode")
    grepable: bool = Field(
        default=False, description="Disable rich/color output for grep-friendly logs"
    )
    workers: int = Field(
        default=4,
        description="Number of concurrent workers for running flows",
    )
    timeout: int = Field(
        default=24 * 60 * 60,
        description="Timeout for running flows in seconds",
    )


def create_settings():
    """
    Create and return the settings instance.
    """
    DEFAULT_CONFIG_CONTENT = """
debug: false
grepable: false
workers: 4
timeout: 86400  # 24 hours
    """
    # check if the config file exists, if not create it
    if not CONFIG_FILE.exists():
        CONFIG_FILE.touch()
        with CONFIG_FILE.open("w") as f:
            f.write(DEFAULT_CONFIG_CONTENT.strip())
    return Settings()


settings = create_settings()
reload_logging_config(settings)
