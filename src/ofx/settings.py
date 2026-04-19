import os
import platform
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    NestedSecretsSettingsSource,
    SettingsConfigDict,
)
from rich.console import Console
from rich.theme import Theme

from ofx.utils.log import reload_logging_config

IS_WINDOWS = platform.system() == "Windows"

BASE_DIR = Path(__file__).parent.absolute()
USER_DIR = Path.home()

BASE_DATA_DIR = Path.home() / ".ofx"
TEMP_DIR = Path(
    tempfile.TemporaryDirectory(prefix=".tmp_r_", dir=str(tempfile.gettempdir())).name
).absolute()
CONFIG_FILE = BASE_DATA_DIR / "config.ini"
CONFIG_YAML = BASE_DATA_DIR / "config.yml"
SECRETS_STORE = Path(os.getenv("OFX_SECRETS_STORE", BASE_DATA_DIR / "secrets.enc"))
SECRETS_DIR = Path(os.getenv("OFX_SECRETS_DIR", BASE_DATA_DIR / "secrets"))
DATA_DIR = Path(__file__).parent / "data"
BUILTIN_WORKFLOWS_DIR = DATA_DIR / "workflows"
DEFAULT_WORKFLOWS_DIR = BASE_DATA_DIR / "workflows"
DEFAULT_WORKFLOWS_DIRS = [Path.cwd().absolute(), DEFAULT_WORKFLOWS_DIR.absolute(), BUILTIN_WORKFLOWS_DIR.absolute()]
DEFAULT_PROJECTS_PATH = BASE_DATA_DIR / "projects"
TOOLS_DIR = USER_DIR / "Tools"
TOOLS_BIN_DIR = TOOLS_DIR / "bin"
USER_EXPLOITS_DIR = BASE_DATA_DIR / "exploits"
USER_SHELLCODE_CONNECTORS_DIR = BASE_DATA_DIR / "shellcode" / "connectors"
USER_WEBSHELL_CONNECTORS_DIR = BASE_DATA_DIR / "webshell" / "connectors"
SESSIONS_DIR = BASE_DATA_DIR / "sessions"
COLLECTIONS_DIR = BASE_DATA_DIR / "collections"
CHANNELS_DIR = TEMP_DIR / "channels"

ALLOWED_WORKFLOW_FILE_EXTENSIONS = (".yml", ".yaml")


def get_workflow_search_dirs() -> list[Path]:
    """Return all workflow search directories including installed collections.

    Combines ``DEFAULT_WORKFLOWS_DIRS`` with paths of every installed
    collection that exists on disk.  Called lazily so that collections
    installed after process start are still found.
    """
    dirs = list(DEFAULT_WORKFLOWS_DIRS)
    # Include installed collections
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
    return settings.github_token.get_secret_value() or _gh_cli_token()


_console = None


def get_console():
    """Get a Rich console with the red team theme applied."""
    global _console
    if _console is None:
        _console = Console(theme=RICH_THEME)
    return _console


class AiSettings(BaseModel):
    """AI assistant configuration.

    Uses the openai SDK — works with any OpenAI-compatible provider.

    Environment variables (OFX_ prefix + double-underscore delimiter):
      OFX_AI__API_KEY    — provider API key (fallback: OPENAI_API_KEY env var)
      OFX_AI__MODEL      — model name (default: gpt-4o)
      OFX_AI__BASE_URL   — base URL for non-OpenAI providers, e.g.:
                             http://localhost:11434/v1   (Ollama)
                             https://api.groq.com/openai/v1  (Groq)
                             https://api.together.xyz/v1  (Together AI)
      OFX_AI__TEMPERATURE        — sampling temperature (default: 0.7)
      OFX_AI__MAX_TOKENS         — max response tokens (default: 8192)
      OFX_AI__MAX_HISTORY_TOKENS — chat history compaction threshold (default: 30000)
    """

    api_key: SecretStr = Field(default=SecretStr(""), description="Provider API key")
    model: str = Field(default="gpt-4o", description="LLM model name")
    base_url: str = Field(
        default="",
        description="Base URL for OpenAI-compatible providers (empty = OpenAI default)",
    )
    temperature: float = Field(default=0.7, description="Sampling temperature")
    max_tokens: int = Field(default=8192, description="Maximum response tokens")
    max_history_tokens: int = Field(
        default=30000, description="Chat history token threshold before compaction"
    )


class RedisRegistrySettings(BaseModel):
    """Redis registry configuration"""

    host: str = Field(default="localhost", description="Redis server host")
    port: int = Field(default=6379, description="Redis server port")
    db: int = Field(default=0, description="Redis database number")
    password: SecretStr | None = Field(default=None, description="Redis password")
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

    # AI assistant settings
    ai: AiSettings = Field(default_factory=AiSettings)

    # Active project name (populated from env var or CLI)
    active_project: str | None = Field(
        default=None, description="Active project name"
    )

    debug: bool = Field(default=False, description="Enable debug mode")
    max_output_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum output size in bytes before truncation",
    )

    max_display_lines: int = Field(
        default=50,
        description="Maximum stdout/stderr lines shown in the console. Full output is saved to log files.",
    )

    auto_store_creds: bool = Field(
        default=False,
        description=(
            "Automatically store discovered UserAccount credentials from task outputs "
            "into the credential store (exegol-history KeePass DB). "
            "Can be overridden per-step with 'store-creds: true/false'."
        ),
    )

    max_parallel_jobs: int = Field(
        default=8,
        description=(
            "Maximum number of jobs that can run concurrently across all stages. "
            "Prevents RAM overload when many jobs are in the same dependency stage. "
            "Set via OFX_MAX_PARALLEL_JOBS env var."
        ),
    )

    memory_limit_percent: int = Field(
        default=90,
        description=(
            "Pause launching new jobs when system memory usage exceeds this percentage. "
            "Set to 0 to disable memory-pressure checks. "
            "Set via OFX_MEMORY_LIMIT_PERCENT env var."
        ),
    )

    default_remote_registry: str = Field(
        default="https://github.com",
        description="Default remote registry URL for cloning repositories",
    )

    # GitHub token
    github_token: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "GitHub personal access token for private collection repos and index. "
            "Set via OFX_GITHUB_TOKEN env var."
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
    channels_dir: str = Field(
        default=str(CHANNELS_DIR),
        description="Directory for inter-job channel files (env: OFX_CHANNELS_DIR)",
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
    registry_cache_enabled: bool = Field(
        default=True,
        description="Enable in-process caching layer for registry reads (env: OFX_REGISTRY_CACHE_ENABLED)",
    )
    registry_cache_ttl: float = Field(
        default=0.25,
        description="Cache TTL in seconds for registry entries (env: OFX_REGISTRY_CACHE_TTL)",
    )
    registry_cache_max_entries: int = Field(
        default=1024,
        description="Maximum cached registry entries per process (env: OFX_REGISTRY_CACHE_MAX_ENTRIES)",
    )
    registry_failover_enabled: bool = Field(
        default=True,
        description="Fall back to in-memory registry on backend errors (env: OFX_REGISTRY_FAILOVER_ENABLED)",
    )

    model_config = SettingsConfigDict(
        env_prefix=f"{app_branding.upper()}_",
        env_file=Path(".env").absolute(),
        env_nested_delimiter="__",
        case_sensitive=False,
        nested_model_default_partial_update=True,
        secrets_dir=SECRETS_DIR.absolute(),
        yaml_file=CONFIG_YAML,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        from pydantic_settings import YamlConfigSettingsSource

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=CONFIG_YAML),
            NestedSecretsSettingsSource(file_secret_settings, secrets_nested_subdir=True, secrets_dir=SECRETS_DIR.absolute()),
        )


# ------------------------------------------------------------------
# Default config.yml generation
# ------------------------------------------------------------------

# Fields excluded from config.yml — internal / runtime-only values that
# should not be persisted or edited by the user.
_CONFIG_EXCLUDE_FIELDS = frozenset({
    "app_name",
    "app_branding",
    "active_project",
    "channels_dir",
})

_CONFIG_YAML_HEADER = """\
# OFX Configuration — ~/.ofx/config.yml
# Environment variables (OFX_ prefix) override values set here.
# SecretStr values (github_token, ai.api_key, registry passwords)
# won't be leaked in logs or repr().
"""


def _dump_default_config() -> str:
    """Build a YAML string with all user-facing settings and their defaults."""
    import yaml

    defaults = Settings()
    data: dict = {}

    for name, _field_info in Settings.model_fields.items():
        if name in _CONFIG_EXCLUDE_FIELDS:
            continue
        value = getattr(defaults, name)

        # Unwrap SecretStr to plain string for YAML serialization
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        # Serialize nested BaseModel to dict, unwrapping SecretStr inside
        elif isinstance(value, BaseModel):
            raw = value.model_dump()
            for k, v in raw.items():
                if isinstance(v, SecretStr):
                    raw[k] = v.get_secret_value()
                # Also handle the field on the actual model instance
                actual = getattr(value, k, v)
                if isinstance(actual, SecretStr):
                    raw[k] = actual.get_secret_value()
            value = raw
        # Convert Path-like objects to strings
        elif isinstance(value, Path):
            value = str(value)

        data[name] = value

    body = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return _CONFIG_YAML_HEADER + body


def _ensure_default_config() -> None:
    """Create ``~/.ofx/config.yml`` with all defaults on first run."""
    if not CONFIG_YAML.exists():
        try:
            CONFIG_YAML.write_text(_dump_default_config())
        except OSError:
            pass


_ensure_default_config()

settings = Settings()
reload_logging_config(settings)
