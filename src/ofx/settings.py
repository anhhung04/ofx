import os
import platform
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.theme import Theme

from ofx.utils.log import reload_logging_config

IS_WINDOWS = platform.system() == "Windows"

BASE_DIR = Path(__file__).parent.absolute()
USER_DIR = Path.home()

BASE_DATA_DIR = Path.home() / ".ofx"
TEMP_DIR = Path(
    tempfile.TemporaryDirectory(prefix="ofx_", dir=str(tempfile.gettempdir())).name
).absolute()
CONFIG_FILE = BASE_DATA_DIR / "config.ini"
SECRETS_STORE = Path(os.getenv("OFX_SECRETS_STORE", BASE_DATA_DIR / "secrets.enc"))
SECRETS_DIR = Path(os.getenv("OFX_SECRETS_DIR", BASE_DATA_DIR / "secrets"))
DEFAULT_WORKFLOWS_DIR = BASE_DATA_DIR / "workflows"
DEFAULT_WORKFLOWS_DIRS = [Path.cwd().absolute(), DEFAULT_WORKFLOWS_DIR.absolute()]
DEFAULT_PROJECTS_PATH = BASE_DATA_DIR / "projects"
TOOLS_DIR = USER_DIR / "Tools"
TOOLS_BIN_DIR = TOOLS_DIR / "bin"
DATA_DIR = Path(__file__).parent / "data"
USER_EXPLOITS_DIR = BASE_DATA_DIR / "exploits"
USER_SHELLCODE_CONNECTORS_DIR = BASE_DATA_DIR / "shellcode" / "connectors"
USER_WEBSHELL_CONNECTORS_DIR = BASE_DATA_DIR / "webshell" / "connectors"
SESSIONS_DIR = BASE_DATA_DIR / "sessions"
COLLECTIONS_DIR = BASE_DATA_DIR / "collections"
SCRIPT_COMMUNICATION_REGISTRY = TEMP_DIR / "script_channels.json"
CHANNELS_DIR = TEMP_DIR / "channels"

ALLOWED_WORKFLOW_FILE_EXTENSIONS = (".yml", ".yaml")


def get_workflow_search_dirs() -> list[Path]:
    """Return all workflow search directories including installed collections.

    Combines ``DEFAULT_WORKFLOWS_DIRS`` with paths of every installed
    collection that exists on disk.  Called lazily so that collections
    installed after process start are still found.
    """
    dirs = list(DEFAULT_WORKFLOWS_DIRS)
    collections_dir = COLLECTIONS_DIR
    if collections_dir.is_dir():
        for child in sorted(collections_dir.iterdir()):
            if child.is_dir() and child.name != "__pycache__":
                abs_child = child.absolute()
                if abs_child not in dirs:
                    dirs.append(abs_child)
    return dirs

DEFAULT_SHELL = "powershell.exe" if IS_WINDOWS else "/bin/bash"

RICH_THEME = Theme(
    {
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "bold cyan",
        "header": "bold red",
        "subheader": "bold magenta",
        "dim": "dim white",
        "bright": "bold white",
        "table.header": "bold red",
        "table.border": "red",
        "table.row": "white",
        "panel.border": "red",
        "panel.header": "bold red",
        "tree": "red",
        "tree.line": "red",
        "progress.description": "cyan",
        "progress.percentage": "green",
        "progress.bar": "red",
        "danger": "bold red on black",
        "alert": "bold yellow on black",
        "good": "bold green",
        "neutral": "white",
        "muted": "dim bright_black",
        "command": "bold cyan",
        "output": "green",
        "stderr": "red",
    }
)


def ensure_dir(path: Path) -> Path:
    """Create directory only if it doesn't exist. Call this when a command needs the directory."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path


ensure_dir(BASE_DATA_DIR)
ensure_dir(TEMP_DIR)
ensure_dir(SECRETS_DIR)


# ------------------------------------------------------------------
# GitHub token resolution: explicit setting → env → gh CLI
# ------------------------------------------------------------------

@lru_cache(maxsize=1)
def _gh_cli_token() -> str:
    """Try to obtain a GitHub token from the ``gh`` CLI.

    Returns an empty string if ``gh`` is not installed or not authenticated.
    The result is cached for the lifetime of the process.
    """
    if not shutil.which("gh"):
        return ""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def get_github_token() -> str:
    """Resolve a GitHub token using the following precedence:

    1. ``OFX_GITHUB_TOKEN`` env var (via ``settings.github_token``)
    2. ``gh auth token`` (if the ``gh`` CLI is installed and authenticated)

    Returns an empty string when no token is available.
    """
    return settings.github_token or _gh_cli_token()


_console = None


def get_console():
    """Get a Rich console with the red team theme applied."""
    global _console
    if _console is None:
        _console = Console(theme=RICH_THEME)
    return _console


class RedisRegistrySettings(BaseModel):
    """Redis registry configuration"""

    host: str = Field(default="localhost", description="Redis server host")
    port: int = Field(default=6379, description="Redis server port")
    db: int = Field(default=0, description="Redis database number")
    password: str | None = Field(default=None, description="Redis password")
    prefix: str = Field(
        default="ofx:run:", description="Key prefix for registry entries"
    )


class MemcachedRegistrySettings(BaseModel):
    """Memcached registry configuration"""

    host: str = Field(default="localhost", description="Memcached server host")
    port: int = Field(default=11211, description="Memcached server port")
    prefix: str = Field(
        default="ofx:run:", description="Key prefix for registry entries"
    )


class EtcdRegistrySettings(BaseModel):
    """etcd registry configuration"""

    host: str = Field(default="localhost", description="etcd server host")
    port: int = Field(default=2379, description="etcd gRPC port")
    prefix: str = Field(
        default="/ofx/run/", description="Key prefix for registry entries"
    )


class Settings(BaseSettings):
    """Application settings or OFX"""

    app_name: str = "Offensive Flow Executor"
    app_branding: str = "ofx"

    debug: bool = Field(default=False, description="Enable debug mode")
    timeout: int = Field(
        default=24 * 60 * 60,
        description="Timeout for running flows in seconds",
    )
    max_output_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum output size in bytes before truncation",
    )

    default_remote_registry: str = Field(
        default="https://github.com",
        description="Default remote registry URL for cloning repositories",
    )

    # Collection / Index Settings
    github_token: str = Field(
        default="",
        description=(
            "GitHub personal access token for private collection repos and index. "
            "Set via OFX_GITHUB_TOKEN env var."
        ),
    )
    collection_index_url: str = Field(
        default="",
        description=(
            "Override the default community index URL. "
            "Set via OFX_COLLECTION_INDEX_URL env var. "
            "Defaults to the ofx-workflows/index repo on GitHub."
        ),
    )

    # Job Registry Settings
    registry_backend: str = Field(
        default="memory",
        description="Job registry backend type: 'memory', 'file', 'redis', 'memcached', or 'etcd'",
    )
    registry_file_path: str | None = Field(
        default=None,
        description="File path for file-based registry (defaults to ~/.ofx/job_registry.json)",
    )
    script_communication_registry_path: str = Field(
        default=str(SCRIPT_COMMUNICATION_REGISTRY),
        description="File path for script inter-job communication registry",
    )
    channels_dir: str = Field(
        default=str(CHANNELS_DIR),
        description="Directory for per-channel files used by inter-job communication",
    )
    registry_redis: RedisRegistrySettings | None = Field(
        default=None,
        description="Redis registry configuration",
    )
    registry_memcached: MemcachedRegistrySettings | None = Field(
        default=None,
        description="Memcached registry configuration",
    )
    registry_etcd: EtcdRegistrySettings | None = Field(
        default=None,
        description="etcd registry configuration",
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
