import logging
import os
import platform
import shutil
import subprocess
import tempfile
from contextlib import suppress
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SecretsSettingsSource, SettingsConfigDict
from rich.console import Console
from rich.theme import Theme

from ofx.utils.file_cleanup import remove_file
from ofx.utils.log import reload_logging_config

IS_WINDOWS = platform.system() == "Windows"

BASE_DIR = Path(__file__).parent.absolute()
USER_DIR = Path.home()

BASE_DATA_DIR = Path.home() / ".ofx"
TEMP_DIR = Path(
    tempfile.mkdtemp(prefix=".tmp_r_", dir=tempfile.gettempdir())
).absolute()
CONFIG_FILE = BASE_DATA_DIR / "config.ini"
CONFIG_YAML = BASE_DATA_DIR / "config.yml"
SECRETS_STORE = Path(os.getenv("OFX_SECRETS_STORE", BASE_DATA_DIR / "secrets.enc"))
SECRETS_DIR = Path(os.getenv("OFX_SECRETS_DIR", BASE_DATA_DIR / "secrets"))
DATA_DIR = Path(__file__).parent / "data"
BUILTIN_WORKFLOWS_DIR = DATA_DIR / "workflows"
DEFAULT_WORKFLOWS_DIR = BASE_DATA_DIR / "workflows"
DEFAULT_WORKFLOWS_DIRS = [
    Path.cwd().absolute(),
    DEFAULT_WORKFLOWS_DIR.absolute(),
    BUILTIN_WORKFLOWS_DIR.absolute(),
]
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
    """Return all workflow search directories including project and collections.

    Search order (first match wins):
    1. Active project's ``workflows/`` directory
    2. Current working directory
    3. User workflows directory (``~/.ofx/workflows/``)
    4. Built-in workflows directory (``src/ofx/data/workflows/``)
    5. Installed collection directories
    """
    dirs: list[Path] = []

    # Active project workflows
    try:
        from ofx.commands.project.project_manager import ProjectManager
        project_wf_dir = ProjectManager.get_project_workflow_dir()
        if project_wf_dir is not None and project_wf_dir.is_dir():
            dirs.append(project_wf_dir)
    except Exception:
        pass

    dirs.extend(DEFAULT_WORKFLOWS_DIRS)

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

def _ensure_default_layout() -> None:
    """Create the standard OFX filesystem layout on first user use."""
    for path in (
        BASE_DATA_DIR,
        SECRETS_DIR,
        DEFAULT_WORKFLOWS_DIR,
        DEFAULT_PROJECTS_PATH,
        USER_EXPLOITS_DIR,
        USER_SHELLCODE_CONNECTORS_DIR,
        USER_WEBSHELL_CONNECTORS_DIR,
        SESSIONS_DIR,
        COLLECTIONS_DIR,
    ):
        ensure_dir(path)

_ensure_default_layout()

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
            start_new_session=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
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

class Settings(BaseSettings):
    """Application settings or OFX"""

    app_name: str = "Offensive Flow Executor"
    app_branding: str = "ofx"

    ai: AiSettings = Field(default_factory=AiSettings)

    active_project: str | None = Field(default=None, description="Active project name")

    debug: bool = Field(default=False, description="Enable debug mode")
    max_output_size: int = Field(
        default=10 * 1024 * 1024,
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

    credential_db_path: str = Field(
        default="~/.exh/DB.kdbx",
        description=(
            "Path to the KeePass database for storing discovered credentials. "
            "Set to a custom path if you use a non-default exegol-history database. "
            "Env: OFX_CREDENTIAL_DB_PATH"
        ),
    )

    credential_key_path: str = Field(
        default="~/.exh/db.key",
        description=(
            "Path to the KeePass key file. "
            "Env: OFX_CREDENTIAL_KEY_PATH"
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

    github_token: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "GitHub personal access token for private collection repos and index. "
            "Set via OFX_GITHUB_TOKEN env var."
        ),
    )

    channels_dir: str = Field(
        default=str(CHANNELS_DIR),
        description="Directory for inter-job channel files (env: OFX_CHANNELS_DIR)",
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
            SecretsSettingsSource(settings_cls, secrets_dir=SECRETS_DIR.absolute()),
        )

_CONFIG_EXCLUDE_FIELDS = frozenset(
    {
        "app_name",
        "app_branding",
        "active_project",
        "channels_dir",
    }
)

_CONFIG_YAML_HEADER = """\
"""

def _dump_default_config() -> str:
    """Build a YAML string with all user-facing settings and their defaults."""
    import yaml

    data: dict = {}

    def _serialize_default(value: object) -> object:
        if isinstance(value, SecretStr):
            return value.get_secret_value()
        if isinstance(value, BaseModel):
            return {
                field_name: _serialize_default(getattr(value, field_name))
                for field_name in value.__class__.model_fields
            }
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {key: _serialize_default(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_serialize_default(item) for item in value]
        return value

    for name, field_info in Settings.model_fields.items():
        if name in _CONFIG_EXCLUDE_FIELDS:
            continue
        value = field_info.get_default(call_default_factory=True)
        data[name] = _serialize_default(value)

    body = yaml.dump(
        data, default_flow_style=False, sort_keys=False, allow_unicode=True
    )
    return _CONFIG_YAML_HEADER + body

def _ensure_default_config() -> None:
    """Create ``~/.ofx/config.yml`` with all defaults on first run."""
    if not CONFIG_YAML.exists():
        with suppress(OSError):
            CONFIG_YAML.write_text(_dump_default_config())

_ensure_default_config()

def update_config_field(key: str, value: object) -> None:
    """Update a single field in ``~/.ofx/config.yml``, preserving other values.

    Uses a lock file and atomic rename so concurrent callers and crashes
    cannot corrupt or lose data.  Locking uses ``fcntl`` on Unix and a
    busy-retry loop on Windows (where ``fcntl`` is unavailable).
    """
    import tempfile

    import yaml

    CONFIG_YAML.parent.mkdir(parents=True, exist_ok=True)
    lock_path = CONFIG_YAML.with_suffix(".yml.lock")

    def _do_update() -> None:
        data: dict = {}
        if CONFIG_YAML.exists():
            try:
                data = yaml.safe_load(CONFIG_YAML.read_text()) or {}
            except Exception:
                logging.debug("Failed to parse config YAML, using empty config", exc_info=True)
                data = {}

        if value is None:
            data.pop(key, None)
        else:
            data[key] = value

        content = _CONFIG_YAML_HEADER + yaml.dump(
            data, default_flow_style=False, sort_keys=False, allow_unicode=True
        )
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=CONFIG_YAML.parent, prefix=".config_tmp_"
        )
        try:
            with os.fdopen(tmp_fd, "w") as fh:
                fh.write(content)
            os.replace(tmp_path, CONFIG_YAML)
        except Exception:
            remove_file(tmp_path)
            raise

    if IS_WINDOWS:
        import time

        deadline = time.monotonic() + 5.0
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    break
                time.sleep(0.05)
        try:
            _do_update()
        finally:
            remove_file(lock_path)
    else:
        import fcntl

        with open(lock_path, "w") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                _do_update()
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

settings = Settings()
reload_logging_config(settings)
