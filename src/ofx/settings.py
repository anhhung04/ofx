import os
import tempfile
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.theme import Theme

from ofx.utils.log import reload_logging_config

BASE_DIR = Path(__file__).parent.absolute()
USER_DIR = Path.home()

BASE_DATA_DIR = Path.home() / ".local" / "share" / "ofx"
TEMP_DIR = Path(tempfile.gettempdir()) / ".ofx"
SECRETS_STORE = Path(os.getenv("OFX_SECRETS_STORE", BASE_DATA_DIR / "secrets.enc"))
SECRETS_DIR = Path(os.getenv("OFX_SECRETS_DIR", BASE_DATA_DIR / "secrets"))
DEFAULT_WORKFLOWS_DIR = BASE_DATA_DIR / "workflows"
DEFAULT_WORKFLOWS_DIRS = [Path.cwd().absolute(), DEFAULT_WORKFLOWS_DIR.absolute()]
DEFAULT_PROJECTS_PATH = Path.home() / "ofx-projects"
TOOLS_DIR = USER_DIR / "Tools"
TOOLS_BIN_DIR = TOOLS_DIR / "bin"
DATA_DIR = Path(__file__).parent / "data"

ALLOWED_WORKFLOW_FILE_EXTENSIONS = (".yml", ".yaml")

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

# Rich theme for red team aesthetic
RICH_THEME = Theme({
    # Status indicators
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "info": "bold cyan",

    # Text styles
    "header": "bold red on black",
    "subheader": "bold magenta",
    "dim": "dim white",
    "bright": "bold white",

    # Table styles
    "table.header": "bold red",
    "table.border": "red",
    "table.row": "white",

    # Panel styles
    "panel.border": "red",
    "panel.header": "bold red",

    # Tree styles
    "tree": "red",
    "tree.line": "red",

    # Progress styles
    "progress.description": "cyan",
    "progress.percentage": "green",
    "progress.bar": "red",

    # Specific colors for red team theme
    "danger": "bold red on black",
    "alert": "bold yellow on black",
    "good": "bold green",
    "neutral": "white",
    "muted": "dim bright_black",

    # Command output styles
    "command": "bold cyan",
    "output": "green",
    "stderr": "red",
})

os.makedirs(BASE_DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(SECRETS_DIR, exist_ok=True)
TOOLS_DIR.mkdir(parents=True, exist_ok=True)
TOOLS_BIN_DIR.mkdir(parents=True, exist_ok=True)


def get_console():
    """Get a Rich console with the red team theme applied."""
    from rich.console import Console
    return Console(theme=RICH_THEME)


class Settings(BaseSettings):
    """Application settings for OFX"""

    app_name: str = "Offensive Flow Executor"
    app_branding: str = "ofx"

    debug: bool = Field(default=False, description="Enable debug mode")
    workers: int = Field(
        default=4,
        description="Number of concurrent workers for running flows",
    )
    timeout: int = Field(
        default=24 * 60 * 60,
        description="Timeout for running flows in seconds",
    )
    max_output_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum output size in bytes before truncation",
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
