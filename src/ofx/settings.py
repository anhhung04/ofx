import os
import tempfile
from pathlib import Path
from pydantic_settings import SettingsConfigDict, BaseSettings

from ofx.utils.log import reload_logging_config

from pydantic import Field
from typing import Union, Literal, Optional, Dict, Any

BASE_DATA_DIR = Path.home() / ".local" / "share" / "ofx"
TEMP_DIR = Path(tempfile.gettempdir()) / ".ofx"
SECRETS_DIR = Path(os.getenv("OFX_SECRETS_DIR", BASE_DATA_DIR / "secrets"))
DEFAULT_WORKFLOWS_DIR = BASE_DATA_DIR / "workflows"

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

os.makedirs(BASE_DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(SECRETS_DIR, exist_ok=True)


class Settings(BaseSettings):
    """
    Application settings for OFX.
    """

    app_name: str = "Offensive Flow Executor"
    app_branding: str = "ofx"

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

    notify_provider: Union[
        None,
        Literal["telegram", "discord", "slack", "pushover"],
    ] = Field(
        default=None,
        description="Notification provider to use for alerts (e.g., 'slack', 'email')",
    )
    notify_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Configuration for the notification provider",
    )

    model_config = SettingsConfigDict(
        secrets_dir=SECRETS_DIR.absolute(),
        env_prefix=f"{app_branding.upper()}_",
        env_file=Path(".env").absolute(),
        env_nested_delimiter="__",
        case_sensitive=False,
        nested_model_default_partial_update=True,
    )


settings = Settings()
reload_logging_config(settings)
