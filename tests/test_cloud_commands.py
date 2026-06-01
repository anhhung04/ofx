from rich.console import Console
from typer.testing import CliRunner
from types import SimpleNamespace

from ofx.commands.cloud.fleets import fleet_app


runner = CliRunner()


class _EmptySessionStore:
    def list_by_fleet_group(self, _fleet_group_id):
        return []


class _Store:
    def save(self, _session):
        return None


class _Session:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "session-1")
        self.instance_ip = kwargs.get("instance_ip", "")
        self.name = kwargs.get("name", "fleet-abcd-0")
        self.fleet_group_id = kwargs.get("fleet_group_id", "")
        self.fleet_index = kwargs.get("fleet_index", -1)
        self.fleet_total = kwargs.get("fleet_total", 0)

    def model_copy(self, update):
        data = self.__dict__.copy()
        data.update(update)
        return _Session(**data)


class _SubmitManager:
    def __init__(self, submitted):
        self.submitted = submitted
        self.store = _Store()

    async def submit(self, *args, **kwargs):
        self.submitted.append(kwargs)
        return _Session(name=kwargs["name"])


class _FleetSession:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "sess-1")
        self.name = kwargs.get("name", "fleet-abcd-0")
        self.project = kwargs.get("project", "")
        self.target = kwargs.get("target", SimpleNamespace(value="cloud"))
        self.status = kwargs.get("status", SimpleNamespace(value="running"))
        self.workflow_file = kwargs.get("workflow_file", "scan.yml")
        self.instance_ip = kwargs.get("instance_ip", "10.0.0.1")
        self.remote_pid = kwargs.get("remote_pid", 1234)
        self.fleet_index = kwargs.get("fleet_index", 0)
        self.error = kwargs.get("error", "")

    def age_display(self):
        return "1h"

    def is_running(self):
        return self.status.value == "running"

    def is_done(self):
        return self.status.value in {"completed", "failed", "canceled", "fetched", "encrypted", "destroyed"}


class _FleetStore:
    def __init__(self, sessions):
        self._sessions = sessions

    def list_by_fleet_group(self, _fleet_group_id):
        return self._sessions


class _FleetManager:
    def __init__(self, *, refreshed=None, fetched=None, canceled=None, store=None):
        self._refreshed = refreshed if refreshed is not None else []
        self._fetched = fetched if fetched is not None else []
        self._canceled = canceled if canceled is not None else []
        self.store = store if store is not None else _Store()

    async def status(self, session_id):
        self._refreshed.append(session_id)
        return _FleetSession(id=session_id, name="fleet-abcd-0", status=SimpleNamespace(value="completed"), fleet_index=0)

    async def fetch(self, session_id, output_dir=None):
        self._fetched.append((session_id, output_dir))
        return output_dir

    async def cancel(self, session_id):
        self._canceled.append(session_id)
        return None


def test_fleet_status_reports_missing_group(monkeypatch):
    console = Console(record=True, width=120)

    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", _EmptySessionStore)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)

    result = runner.invoke(fleet_app, ["status", "fleet-123"])

    assert result.exit_code == 1
    assert "No sessions found for fleet group 'fleet-123'" in console.export_text()


def test_fleet_results_reports_missing_group(monkeypatch):
    console = Console(record=True, width=120)

    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", _EmptySessionStore)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)

    result = runner.invoke(fleet_app, ["results", "fleet-123"])

    assert result.exit_code == 1
    assert "No sessions found for fleet group 'fleet-123'" in console.export_text()


def test_fleet_cancel_reports_missing_group(monkeypatch):
    console = Console(record=True, width=120)

    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", _EmptySessionStore)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)

    result = runner.invoke(fleet_app, ["cancel", "fleet-123"])

    assert result.exit_code == 1
    assert "No sessions found for fleet group 'fleet-123'" in console.export_text()


def test_fleet_run_uses_global_cli_project(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[dict] = []

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "global-proj", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: SimpleNamespace(name="active-proj")),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.parse_key_value_pairs", lambda items: {}, raising=False)
    monkeypatch.setattr("secrets.token_hex", lambda _n: "abcd")

    class FakeSessionManager:
        def __new__(cls):
            return _SubmitManager(submitted)

    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", FakeSessionManager)

    result = runner.invoke(fleet_app, ["run", "scan.yml", "--profile", "demo", "--count", "1"])

    assert result.exit_code == 0
    assert submitted[0]["project"] == "global-proj"


def test_fleet_run_uses_active_project_when_global_missing(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[dict] = []

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: SimpleNamespace(name="active-proj")),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.parse_key_value_pairs", lambda items: {}, raising=False)
    monkeypatch.setattr("secrets.token_hex", lambda _n: "abcd")

    class FakeSessionManager:
        def __new__(cls):
            return _SubmitManager(submitted)

    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", FakeSessionManager)

    result = runner.invoke(fleet_app, ["run", "scan.yml", "--profile", "demo", "--count", "1"])

    assert result.exit_code == 0
    assert submitted[0]["project"] == "active-proj"


def test_fleet_run_uses_module_cli_env_vars(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[dict] = []

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: None),
        raising=False,
    )
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.get_cli_env_vars",
        lambda: {"OFX_FLAG": "patched"},
        raising=False,
    )
    monkeypatch.setattr("secrets.token_hex", lambda _n: "abcd")

    class FakeSessionManager:
        def __new__(cls):
            return _SubmitManager(submitted)

    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", FakeSessionManager)

    result = runner.invoke(fleet_app, ["run", "scan.yml", "--profile", "demo", "--count", "1"])

    assert result.exit_code == 0
    assert submitted[0]["env"] == {"OFX_FLAG": "patched"}


def test_fleet_run_uses_module_key_value_parser(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[dict] = []

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: None),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.parse_key_value_pairs",
        lambda items: {"mode": "patched"},
        raising=False,
    )
    monkeypatch.setattr("secrets.token_hex", lambda _n: "abcd")

    class FakeSessionManager:
        def __new__(cls):
            return _SubmitManager(submitted)

    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", FakeSessionManager)

    result = runner.invoke(
        fleet_app,
        ["run", "scan.yml", "--profile", "demo", "--count", "1", "--input", "mode=cli"],
    )

    assert result.exit_code == 0
    assert submitted[0]["inputs"] == {"mode": "patched"}


def test_fleet_run_uses_module_session_manager(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[dict] = []

    class BrokenManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionManager")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: None),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.parse_key_value_pairs", lambda items: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionManager", lambda: _SubmitManager(submitted), raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", BrokenManager)
    monkeypatch.setattr("secrets.token_hex", lambda _n: "abcd")

    result = runner.invoke(fleet_app, ["run", "scan.yml", "--profile", "demo", "--count", "1"])

    assert result.exit_code == 0
    assert submitted[0]["name"] == "fleet-abcd-0"


def test_fleet_run_uses_module_session_target(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[dict] = []

    class BrokenTarget:
        LOCAL = SimpleNamespace(value="broken-local")
        CLOUD = SimpleNamespace(value="broken-cloud")

    fake_target = SimpleNamespace(
        LOCAL=SimpleNamespace(value="module-local"),
        CLOUD=SimpleNamespace(value="module-cloud"),
    )

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: None),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.parse_key_value_pairs", lambda items: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionManager", lambda: _SubmitManager(submitted), raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionTarget", fake_target, raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionTarget", BrokenTarget)
    monkeypatch.setattr("secrets.token_hex", lambda _n: "abcd")

    result = runner.invoke(fleet_app, ["run", "scan.yml", "--profile", "demo", "--count", "1"])

    assert result.exit_code == 0
    assert submitted[0]["target"].value == "module-cloud"


def test_fleet_run_uses_module_input_parser_and_distributor(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[dict] = []
    parser_calls: list[str] = []
    distributor_calls: list[tuple[list[str], int, str]] = []

    class BrokenParser:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.fleet_input.FleetInputParser")

    class BrokenDistributor:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.fleet_distributor.FleetDistributor")

    class FakeParser:
        def parse(self, targets):
            parser_calls.append(targets)
            return ["10.0.0.1"]

    class FakeDistributor:
        def distribute(self, targets, count, distribution):
            distributor_calls.append((targets, count, distribution))
            return [["10.0.0.1"]]

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: None),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.parse_key_value_pairs", lambda items: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionManager", lambda: _SubmitManager(submitted), raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.FleetInputParser", FakeParser, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.FleetDistributor", FakeDistributor, raising=False)
    monkeypatch.setattr("ofx.cloud.fleet_input.FleetInputParser", BrokenParser)
    monkeypatch.setattr("ofx.cloud.fleet_distributor.FleetDistributor", BrokenDistributor)
    monkeypatch.setattr("secrets.token_hex", lambda _n: "abcd")

    result = runner.invoke(
        fleet_app,
        ["run", "scan.yml", "--profile", "demo", "--targets", "targets.txt", "--count", "1"],
    )

    assert result.exit_code == 0
    assert parser_calls == ["targets.txt"]
    assert distributor_calls == [(["10.0.0.1"], 1, "chunk")]
    assert "targets_file" in submitted[0]["inputs"]


def test_fleet_run_empty_distributed_targets_reports_error(monkeypatch):
    console = Console(record=True, width=120)

    class FakeParser:
        def parse(self, targets):
            return ["10.0.0.1"]

    class FakeDistributor:
        def distribute(self, targets, count, distribution):
            return []

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: None),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.parse_key_value_pairs", lambda items: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.FleetInputParser", FakeParser, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.FleetDistributor", FakeDistributor, raising=False)

    result = runner.invoke(
        fleet_app,
        ["run", "scan.yml", "--profile", "demo", "--targets", "targets.txt", "--count", "1"],
    )

    assert result.exit_code == 1
    assert "Fleet: no targets after parsing/exclusion. Check --targets." in console.export_text()


def test_fleet_run_saves_fleet_metadata_on_submitted_session(monkeypatch):
    console = Console(record=True, width=120)
    saved_sessions: list[object] = []

    class SavingStore:
        def save(self, session):
            saved_sessions.append(session)

    class SavingManager(_SubmitManager):
        def __init__(self, submitted):
            super().__init__(submitted)
            self.store = SavingStore()

    submitted: list[dict] = []

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(get_active_path=lambda: None),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.parse_key_value_pairs", lambda items: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionManager", lambda: SavingManager(submitted), raising=False)
    monkeypatch.setattr("secrets.token_hex", lambda _n: "abcd")

    result = runner.invoke(fleet_app, ["run", "scan.yml", "--profile", "demo", "--count", "1"])

    assert result.exit_code == 0
    assert len(saved_sessions) == 1
    saved = saved_sessions[0]
    assert saved.fleet_group_id == "abcd"
    assert saved.fleet_index == 0
    assert saved.fleet_total == 1


def test_fleet_status_uses_module_store_and_manager(monkeypatch):
    console = Console(record=True, width=120)
    refreshed: list[str] = []
    sessions = [_FleetSession(id="sess-1", name="fleet-abcd-0", fleet_index=0)]

    class BrokenStore:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionStore")

    class BrokenManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionManager")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionStore", lambda: _FleetStore(sessions), raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionManager", lambda store=None: _FleetManager(refreshed=refreshed, store=store), raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", BrokenStore)
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", BrokenManager)

    result = runner.invoke(fleet_app, ["status", "fleet-123", "--refresh"])

    assert result.exit_code == 0
    assert refreshed == ["sess-1"]
    assert "Fleet Sessions" in console.export_text()


def test_fleet_results_uses_module_store_and_manager(monkeypatch, tmp_path):
    console = Console(record=True, width=120)
    refreshed: list[str] = []
    fetched: list[tuple[str, object]] = []
    sessions = [
        _FleetSession(
            id="sess-1",
            name="fleet-abcd-0",
            fleet_index=0,
            status=SimpleNamespace(value="completed"),
        )
    ]

    class BrokenStore:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionStore")

    class BrokenManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionManager")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionStore", lambda: _FleetStore(sessions), raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionManager", lambda store=None: _FleetManager(refreshed=refreshed, fetched=fetched, store=store), raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", BrokenStore)
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", BrokenManager)

    result = runner.invoke(fleet_app, ["results", "fleet-123", "--output", str(tmp_path)])

    assert result.exit_code == 0
    assert refreshed == ["sess-1"]
    assert fetched and fetched[0][0] == "sess-1"
    assert "Fetched 1/1 session results" in console.export_text()


def test_fleet_cancel_uses_module_store_and_manager(monkeypatch):
    console = Console(record=True, width=120)
    canceled: list[str] = []
    sessions = [_FleetSession(id="sess-1", name="fleet-abcd-0", fleet_index=0)]

    class BrokenStore:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionStore")

    class BrokenManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionManager")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionStore", lambda: _FleetStore(sessions), raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionManager", lambda store=None: _FleetManager(canceled=canceled, store=store), raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", BrokenStore)
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", BrokenManager)

    result = runner.invoke(fleet_app, ["cancel", "fleet-123", "--force"])

    assert result.exit_code == 0
    assert canceled == ["sess-1"]
    assert "Canceled 1/1 sessions" in console.export_text()


def test_fleet_results_uses_module_project_manager(monkeypatch, tmp_path):
    console = Console(record=True, width=120)
    refreshed: list[str] = []
    fetched: list[tuple[str, object]] = []
    project_path = tmp_path / "project"
    project_path.mkdir()
    sessions = [
        _FleetSession(
            id="sess-1",
            name="fleet-abcd-0",
            fleet_index=0,
            status=SimpleNamespace(value="completed"),
            project="demo-proj",
        )
    ]

    class BrokenProjectManager:
        @staticmethod
        def resolve_path(_name):
            raise RuntimeError("should not use ofx.commands.project.project_manager.ProjectManager")

    class ProjectAwareManager(_FleetManager):
        async def status(self, session_id):
            self._refreshed.append(session_id)
            return _FleetSession(
                id=session_id,
                name="fleet-abcd-0",
                status=SimpleNamespace(value="completed"),
                fleet_index=0,
                project="demo-proj",
            )

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionStore", lambda: _FleetStore(sessions), raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionManager", lambda store=None: ProjectAwareManager(refreshed=refreshed, fetched=fetched, store=store), raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ProjectManager",
        SimpleNamespace(resolve_path=lambda _name: str(project_path)),
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.project.project_manager.ProjectManager", BrokenProjectManager)

    result = runner.invoke(fleet_app, ["results", "fleet-123"])

    assert result.exit_code == 0
    assert fetched
    assert str(project_path / "evidence" / "sessions" / "fleet-fleet-123") in console.export_text()


def test_fleet_results_uses_module_temp_dir_settings(monkeypatch, tmp_path):
    console = Console(record=True, width=120)
    refreshed: list[str] = []
    fetched: list[tuple[str, object]] = []
    sessions = [
        _FleetSession(
            id="sess-1",
            name="fleet-abcd-0",
            fleet_index=0,
            status=SimpleNamespace(value="completed"),
            project="",
        )
    ]
    ensured_dirs: list[object] = []
    base_dir = tmp_path / "module-temp"

    class BrokenEnsureDir:
        def __call__(self, _path):
            raise RuntimeError("should not use ofx.settings.ensure_dir")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionStore", lambda: _FleetStore(sessions), raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.SessionManager",
        lambda store=None: _FleetManager(refreshed=refreshed, fetched=fetched, store=store),
        raising=False,
    )
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.ensure_dir",
        lambda path: ensured_dirs.append(path) or base_dir,
        raising=False,
    )
    monkeypatch.setattr("ofx.commands.cloud.fleets.TEMP_DIR", "module-temp-root", raising=False)
    monkeypatch.setattr("ofx.settings.ensure_dir", BrokenEnsureDir())

    result = runner.invoke(fleet_app, ["results", "fleet-123"])

    assert result.exit_code == 0
    assert ensured_dirs == ["module-temp-root"]
    assert fetched == [("sess-1", base_dir / "fleet-fleet-123" / "instance-0")]


def test_fleet_results_uses_module_encrypt_results(monkeypatch, tmp_path):
    console = Console(record=True, width=120)
    sessions = [
        _FleetSession(
            id="sess-1",
            name="fleet-abcd-0",
            fleet_index=0,
            status=SimpleNamespace(value="completed"),
        )
    ]
    encrypted_calls: list[tuple[object, str]] = []
    output_dir = tmp_path / "results"

    class BrokenEncrypt:
        def __call__(self, _path, _passphrase):
            raise RuntimeError("should not use ofx.cloud.sessions.encryption.encrypt_results")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionStore", lambda: _FleetStore(sessions), raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.SessionManager",
        lambda store=None: _FleetManager(store=store),
        raising=False,
    )
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.encrypt_results",
        lambda path, passphrase: encrypted_calls.append((path, passphrase)) or (tmp_path / "fleet.enc"),
        raising=False,
    )
    monkeypatch.setattr("ofx.cloud.sessions.encryption.encrypt_results", BrokenEncrypt())

    result = runner.invoke(
        fleet_app,
        ["results", "fleet-123", "--output", str(output_dir), "--passphrase", "pw"],
    )

    assert result.exit_code == 0
    assert encrypted_calls == [(output_dir, "pw")]
    assert "Encrypted →" in console.export_text()


def test_fleet_results_no_fetchable_shows_dim_message(monkeypatch):
    console = Console(record=True, width=120)
    sessions = [
        _FleetSession(
            id="sess-1",
            name="fleet-abcd-0",
            fleet_index=0,
            status=SimpleNamespace(value="destroyed"),
        )
    ]

    class DestroyedManager(_FleetManager):
        async def status(self, session_id):
            return _FleetSession(
                id=session_id,
                name="fleet-abcd-0",
                fleet_index=0,
                status=SimpleNamespace(value="destroyed"),
            )

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionStore", lambda: _FleetStore(sessions), raising=False)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.SessionManager",
        lambda store=None: DestroyedManager(store=store),
        raising=False,
    )

    result = runner.invoke(fleet_app, ["results", "fleet-123"])

    assert result.exit_code == 0
    assert "No results to fetch." in console.export_text()


def test_fleet_cancel_no_running_shows_dim_message(monkeypatch):
    console = Console(record=True, width=120)
    sessions = [
        _FleetSession(
            id="sess-1",
            name="fleet-abcd-0",
            fleet_index=0,
            status=SimpleNamespace(value="completed"),
        )
    ]

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.SessionStore", lambda: _FleetStore(sessions), raising=False)

    result = runner.invoke(fleet_app, ["cancel", "fleet-123", "--force"])

    assert result.exit_code == 0
    assert "No running sessions to cancel." in console.export_text()


def test_fleet_destroy_no_matching_instances_shows_dim_message(monkeypatch):
    console = Console(record=True, width=120)

    class FakeCloud:
        async def list_instances(self):
            return []

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.run_cloud_sync", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("ofx.commands.cloud.fleets.create_cloud_provider", lambda profile, provider: (None, FakeCloud()))

    result = runner.invoke(fleet_app, ["destroy", "--provider", "demo"])

    assert result.exit_code == 0
    assert "No matching instances found." in console.export_text()


def test_fleet_destroy_reports_destroyed_count(monkeypatch):
    console = Console(record=True, width=120)

    class FakeInstance:
        def __init__(self, instance_id, name, ip):
            self.instance_id = instance_id
            self.name = name
            self.ip = ip
            self.tags = []

    class FakeCloud:
        async def list_instances(self):
            return [FakeInstance("i-1", "demo-1", "1.1.1.1")]

        async def destroy_instance(self, instance_id):
            return None

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.run_cloud_sync", lambda *_args, **_kwargs: [FakeInstance("i-1", "demo-1", "1.1.1.1")])
    monkeypatch.setattr("ofx.commands.cloud.fleets.create_cloud_provider", lambda profile, provider: (None, FakeCloud()))

    result = runner.invoke(fleet_app, ["destroy", "--provider", "demo", "--prefix", "demo", "--force"])

    assert result.exit_code == 0
    assert "Destroyed 1/1 instances." in console.export_text()


def test_fleet_destroy_prints_target_heading(monkeypatch):
    console = Console(record=True, width=120)

    class FakeInstance:
        def __init__(self, instance_id, name, ip):
            self.instance_id = instance_id
            self.name = name
            self.ip = ip
            self.tags = []

    class FakeCloud:
        async def list_instances(self):
            return [FakeInstance("i-1", "demo-1", "1.1.1.1")]

        async def destroy_instance(self, instance_id):
            return None

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.create_cloud_provider", lambda profile, provider: (None, FakeCloud()))
    monkeypatch.setattr("ofx.commands.cloud.fleets.run_cloud_sync", lambda *_args, **_kwargs: [FakeInstance("i-1", "demo-1", "1.1.1.1")])

    result = runner.invoke(fleet_app, ["destroy", "--provider", "demo", "--prefix", "demo", "--force"])

    assert result.exit_code == 0
    assert "Found 1 instances to destroy:" in console.export_text()


def test_fleet_create_requires_provider_or_profile(monkeypatch):
    console = Console(record=True, width=120)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)

    result = runner.invoke(fleet_app, ["create", "1"])

    assert result.exit_code == 1
    assert "Specify --provider or --profile" in console.export_text()


def test_fleet_run_requires_profile(monkeypatch):
    console = Console(record=True, width=120)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.ProjectManager", SimpleNamespace(get_active_path=lambda: None), raising=False)
    monkeypatch.setattr("ofx.commands.cloud.fleets.parse_key_value_pairs", lambda items: {}, raising=False)

    result = runner.invoke(fleet_app, ["run", "scan.yml"])

    assert result.exit_code == 1
    assert "Fleet run requires --profile for cloud execution" in console.export_text()


def test_fleet_create_no_instances_created_reports_error(monkeypatch):
    console = Console(record=True, width=120)

    class FakeCloud:
        async def create_instance(self, cfg):
            raise RuntimeError("boom")

        async def wait_until_ready(self, instance_id):
            return None

        async def get_instance(self, instance_id):
            return None

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.cloud.CloudProviderRegistry.create", lambda provider: FakeCloud())

    result = runner.invoke(fleet_app, ["create", "1", "--provider", "demo"])

    assert result.exit_code == 1
    assert "No instances created." in console.export_text()


def test_fleet_create_uses_module_profile_manager(monkeypatch):
    console = Console(record=True, width=120)
    created_providers: list[str] = []

    class FakeConfig:
        provider = "module-provider"
        region = "module-region"
        size = "module-size"
        image = "module-image"

    class FakeProfileManager:
        def as_cloud_config(self, profile):
            assert profile == "demo"
            return FakeConfig()

    def broken_profile_manager_getter():
        raise RuntimeError("should not use ofx.cloud.config.get_cloud_profile_manager")

    class FakeInstance:
        def __init__(self, instance_id, ip=None):
            self.instance_id = instance_id
            self.ip = ip

    class FakeCloud:
        async def create_instance(self, cfg):
            assert cfg.provider == "module-provider"
            assert cfg.region == "module-region"
            assert cfg.size == "module-size"
            assert cfg.image == "module-image"
            return FakeInstance("i-1")

        async def wait_until_ready(self, instance_id):
            return None

        async def get_instance(self, instance_id):
            return FakeInstance(instance_id, "1.1.1.1")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.get_cloud_profile_manager",
        lambda: FakeProfileManager(),
        raising=False,
    )
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.CloudProviderRegistry",
        SimpleNamespace(
            create=lambda provider: created_providers.append(provider) or FakeCloud()
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "ofx.cloud.config.get_cloud_profile_manager",
        broken_profile_manager_getter,
    )

    result = runner.invoke(fleet_app, ["create", "1", "--profile", "demo"])

    assert result.exit_code == 0
    assert created_providers == ["module-provider"]


def test_fleet_create_uses_module_provider_registry(monkeypatch):
    console = Console(record=True, width=120)
    created_providers: list[str] = []

    class BrokenRegistry:
        @staticmethod
        def create(_provider):
            raise RuntimeError("should not use ofx.cloud.CloudProviderRegistry")

    class FakeInstance:
        def __init__(self, instance_id, ip=None):
            self.instance_id = instance_id
            self.ip = ip

    class FakeCloud:
        async def create_instance(self, cfg):
            return FakeInstance("i-1")

        async def wait_until_ready(self, instance_id):
            return None

        async def get_instance(self, instance_id):
            return FakeInstance(instance_id, "1.1.1.1")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr(
        "ofx.commands.cloud.fleets.CloudProviderRegistry",
        SimpleNamespace(
            create=lambda provider: created_providers.append(provider) or FakeCloud()
        ),
        raising=False,
    )
    monkeypatch.setattr("ofx.cloud.CloudProviderRegistry", BrokenRegistry)

    result = runner.invoke(fleet_app, ["create", "1", "--provider", "demo"])

    assert result.exit_code == 0
    assert created_providers == ["demo"]


def test_fleet_create_reports_ready_count(monkeypatch):
    console = Console(record=True, width=120)

    class FakeInstance:
        def __init__(self, instance_id, ip=None):
            self.instance_id = instance_id
            self.ip = ip

    class FakeCloud:
        async def create_instance(self, cfg):
            return FakeInstance("i-1")

        async def wait_until_ready(self, instance_id):
            return None

        async def get_instance(self, instance_id):
            return FakeInstance(instance_id, "1.1.1.1")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.cloud.CloudProviderRegistry.create", lambda provider: FakeCloud())

    result = runner.invoke(fleet_app, ["create", "1", "--provider", "demo"])

    assert result.exit_code == 0
    output = console.export_text()
    assert "Created i-1" in output
    assert "Fleet of 1 instances ready." in output


def test_fleet_create_reports_wait_warning(monkeypatch):
    console = Console(record=True, width=120)

    class FakeInstance:
        def __init__(self, instance_id, ip=None):
            self.instance_id = instance_id
            self.ip = ip

    class FakeCloud:
        async def create_instance(self, cfg):
            return FakeInstance("i-1")

        async def wait_until_ready(self, instance_id):
            raise TimeoutError("timed out")

        async def get_instance(self, instance_id):
            return FakeInstance(instance_id, "1.1.1.1")

    monkeypatch.setattr("ofx.commands.cloud.fleets.get_console", lambda: console)
    monkeypatch.setattr("ofx.cloud.CloudProviderRegistry.create", lambda provider: FakeCloud())

    result = runner.invoke(fleet_app, ["create", "1", "--provider", "demo"])

    assert result.exit_code == 0
    output = console.export_text()
    assert "i-1: timed out" in output
    assert "Fleet of 1 instances ready." in output
