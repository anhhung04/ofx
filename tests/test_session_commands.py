from datetime import UTC, datetime, timedelta
import importlib
from types import SimpleNamespace

import typer
from rich.console import Console
from typer.testing import CliRunner

from ofx.commands.session.app import app


session_app_module = importlib.import_module("ofx.commands.session.app")


runner = CliRunner()


class _AsyncSessionManager:
    def __init__(self, *, session=None, output=None, status_calls=None, log_calls=None):
        self._session = session
        self._output = output
        self._status_calls = status_calls if status_calls is not None else []
        self._log_calls = log_calls if log_calls is not None else []

    async def status(self, session_id):
        self._status_calls.append(session_id)
        return self._session

    async def logs(self, session_id, tail=50):
        self._log_calls.append((session_id, tail))
        return self._output


class _SubmitSession:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "sess-1")
        self.name = kwargs.get("name", "demo")
        self.project = kwargs.get("project", "")
        self.target = kwargs.get("target", SimpleNamespace(value="local"))
        self.status = kwargs.get("status", SimpleNamespace(value="queued"))
        self.workflow_file = kwargs.get("workflow_file", "scan.yml")
        self.job_id = kwargs.get("job_id", "")
        self.auto_destroy = kwargs.get("auto_destroy", True)
        self.remote_pid = None
        self.instance_ip = ""
        self.encrypted = False
        self.results_path = ""
        self.error = ""
        self.age_display = lambda: "0s"


class _SubmitManager:
    def __init__(self, submitted):
        self.submitted = submitted

    async def submit(self, workflow, **kwargs):
        self.submitted.append((workflow, kwargs))
        return _SubmitSession(
            name=kwargs.get("name", "demo"),
            project=kwargs.get("project", ""),
            target=kwargs.get("target"),
            workflow_file=workflow,
            job_id=kwargs.get("job_id", ""),
        )


class _SessionStoreStub:
    def __init__(self, sessions=None):
        self._sessions = sessions if sessions is not None else []

    def list_sessions(self, **_kwargs):
        return self._sessions

    def clean(self, *, older_than_seconds=None, statuses=None):
        return 0


class _FakeSessionStatus:
    COMPLETED = SimpleNamespace(value="completed")
    FAILED = SimpleNamespace(value="failed")

    def __init__(self, value):
        valid = {"completed", "failed"}
        if value not in valid:
            raise ValueError(value)
        self.value = value

    def __eq__(self, other):
        return getattr(other, "value", None) == self.value

    @classmethod
    def __iter__(cls):
        return iter([cls.COMPLETED, cls.FAILED])


def test_session_clean_rejects_invalid_duration(monkeypatch):
    errors: list[tuple[str, str, str | None]] = []

    def fake_error_exit(title, message, details=None):
        errors.append((title, message, details))
        raise typer.Exit(code=1)

    monkeypatch.setattr(session_app_module, "error_exit", fake_error_exit)

    result = runner.invoke(app, ["clean", "--older-than", "bogus"])

    assert result.exit_code == 1
    assert errors == [
        (
            "Invalid duration",
            "Invalid duration: bogus",
            "Examples: 7d, 24h, 30m, 3600s",
        )
    ]


def test_session_clean_passes_parsed_age_seconds_to_store(monkeypatch):
    calls: list[tuple[int | None, object]] = []

    class FakeStore:
        def list_sessions(self):
            return [
                SimpleNamespace(
                    id="sess-1",
                    name="demo",
                    status=SessionStatus.COMPLETED,
                    started_at=datetime.now(UTC) - timedelta(hours=2),
                    age_display=lambda: "2h",
                )
            ]

        def clean(self, *, older_than_seconds=None, statuses=None):
            calls.append((older_than_seconds, statuses))
            return 1

    from ofx.cloud.sessions.models import SessionStatus

    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", FakeStore)
    monkeypatch.setattr(
        session_app_module,
        "get_console",
        lambda: SimpleNamespace(print=lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)

    result = runner.invoke(
        app,
        ["clean", "--older-than", "90m", "--status", "completed", "--yes"],
    )

    assert result.exit_code == 0
    assert calls == [(5400, [SessionStatus.COMPLETED])]


def test_session_guard_passes_parsed_age_seconds_to_store(monkeypatch):
    calls: list[tuple[int | None, object]] = []

    class FakeStore:
        def clean(self, *, older_than_seconds=None, statuses=None):
            calls.append((older_than_seconds, statuses))
            return 2

    from ofx.cloud.sessions.models import SessionStatus

    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", FakeStore)
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)

    result = runner.invoke(
        app,
        ["guard", "--older-than", "2h", "--status", "completed,failed"],
    )

    assert result.exit_code == 0
    assert calls == [(7200, [SessionStatus.COMPLETED, SessionStatus.FAILED])]


def test_session_status_uses_module_session_manager(monkeypatch):
    console = Console(record=True, width=120)
    status_calls: list[str] = []
    session = SimpleNamespace(
        id="sess-1",
        name="demo",
        project="",
        target=SimpleNamespace(value="local"),
        status=SimpleNamespace(value="completed"),
        workflow_file="scan.yml",
        job_id="",
        remote_pid=None,
        instance_ip="",
        encrypted=False,
        results_path="",
        error="",
        age_display=lambda: "1h",
    )

    monkeypatch.setattr(
        session_app_module,
        "SessionManager",
        lambda: _AsyncSessionManager(session=session, status_calls=status_calls),
        raising=False,
    )
    monkeypatch.setattr(session_app_module, "get_console", lambda: console)

    result = runner.invoke(app, ["status", "sess-1"])

    assert result.exit_code == 0
    assert status_calls == ["sess-1"]
    assert "sess-1" in console.export_text()


def test_session_logs_uses_module_session_manager(monkeypatch):
    console = Console(record=True, width=120)
    log_calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        session_app_module,
        "SessionManager",
        lambda: _AsyncSessionManager(output="log line", log_calls=log_calls),
        raising=False,
    )
    monkeypatch.setattr(session_app_module, "get_console", lambda: console)

    result = runner.invoke(app, ["logs", "sess-1", "--tail", "25"])

    assert result.exit_code == 0
    assert log_calls == [("sess-1", 25)]
    assert "log line" in console.export_text()


def test_session_fetch_reports_result_path(monkeypatch, tmp_path):
    seen: list[tuple[str, str, Path | None]] = []
    successes: list[tuple[str, str, dict | None]] = []

    class FakeManager:
        async def fetch(self, session_id, *, passphrase="", output_dir=None):
            seen.append((session_id, passphrase, output_dir))
            return tmp_path / "results"

    monkeypatch.setattr(session_app_module, "SessionManager", lambda: FakeManager(), raising=False)
    monkeypatch.setattr(
        session_app_module,
        "print_success",
        lambda title, msg, details=None: successes.append((title, msg, details)),
    )

    result = runner.invoke(app, ["fetch", "sess-1", "--passphrase", "pw", "--output", str(tmp_path)])

    assert result.exit_code == 0
    assert seen == [("sess-1", "pw", tmp_path)]
    assert successes == [
        ("Results", "Results fetched and encrypted.", {"Path": str(tmp_path / "results")})
    ]


def test_session_decrypt_reports_result_path(monkeypatch, tmp_path):
    seen: list[tuple[str, str, Path | None]] = []
    successes: list[tuple[str, str, dict | None]] = []

    class FakeManager:
        async def decrypt(self, session_id, *, passphrase, output_dir=None):
            seen.append((session_id, passphrase, output_dir))
            return tmp_path / "decrypted"

    monkeypatch.setattr(session_app_module, "SessionManager", lambda: FakeManager(), raising=False)
    monkeypatch.setattr(
        session_app_module,
        "print_success",
        lambda title, msg, details=None: successes.append((title, msg, details)),
    )

    result = runner.invoke(
        app,
        ["decrypt", "sess-1", "--passphrase", "pw", "--output", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert seen == [("sess-1", "pw", tmp_path)]
    assert successes == [
        ("Results", "Results decrypted.", {"Path": str(tmp_path / "decrypted")})
    ]


def test_session_submit_uses_module_cli_env_vars(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[tuple[str, dict]] = []

    monkeypatch.setattr(session_app_module, "get_console", lambda: console)
    monkeypatch.setattr(session_app_module, "get_cli_env_vars", lambda: {"OFX_FLAG": "patched"}, raising=False)
    monkeypatch.setattr(session_app_module, "get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "print_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "_session_detail_table", lambda _session: "details")
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", lambda: _SubmitManager(submitted))

    result = runner.invoke(app, ["submit", "scan.yml"])

    assert result.exit_code == 0
    assert submitted[0][1]["env"] == {"OFX_FLAG": "patched"}


def test_session_submit_uses_module_key_value_parser(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[tuple[str, dict]] = []

    monkeypatch.setattr(session_app_module, "get_console", lambda: console)
    monkeypatch.setattr(session_app_module, "get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr(session_app_module, "get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(session_app_module, "parse_key_value_pairs", lambda _items: {"mode": "patched"}, raising=False)
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "print_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "_session_detail_table", lambda _session: "details")
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", lambda: _SubmitManager(submitted))

    result = runner.invoke(app, ["submit", "scan.yml", "--input", "mode=cli"])

    assert result.exit_code == 0
    assert submitted[0][1]["inputs"] == {"mode": "patched"}


def test_session_submit_uses_module_cli_project(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[tuple[str, dict]] = []

    monkeypatch.setattr(session_app_module, "get_console", lambda: console)
    monkeypatch.setattr(session_app_module, "get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr(session_app_module, "get_cli_project", lambda: "global-proj", raising=False)
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "print_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "_session_detail_table", lambda _session: "details")
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", lambda: _SubmitManager(submitted))

    result = runner.invoke(app, ["submit", "scan.yml"])

    assert result.exit_code == 0
    assert submitted[0][1]["project"] == "global-proj"


def test_session_submit_uses_module_active_project_when_cli_missing(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[tuple[str, dict]] = []

    monkeypatch.setattr(session_app_module, "get_console", lambda: console)
    monkeypatch.setattr(session_app_module, "get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr(session_app_module, "get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(
        session_app_module,
        "ProjectManager",
        SimpleNamespace(get_active_path=lambda: SimpleNamespace(name="active-proj")),
        raising=False,
    )
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "print_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "_session_detail_table", lambda _session: "details")
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", lambda: _SubmitManager(submitted))

    result = runner.invoke(app, ["submit", "scan.yml"])

    assert result.exit_code == 0
    assert submitted[0][1]["project"] == "active-proj"


def test_session_submit_uses_module_session_manager(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[tuple[str, dict]] = []

    class BrokenManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionManager")

    monkeypatch.setattr(session_app_module, "get_console", lambda: console)
    monkeypatch.setattr(session_app_module, "get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr(session_app_module, "get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "print_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "_session_detail_table", lambda _session: "details")
    monkeypatch.setattr(session_app_module, "ProjectManager", SimpleNamespace(get_active_path=lambda: None), raising=False)
    monkeypatch.setattr(session_app_module, "SessionManager", lambda: _SubmitManager(submitted), raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", BrokenManager)

    result = runner.invoke(app, ["submit", "scan.yml"])

    assert result.exit_code == 0
    assert submitted[0][0] == "scan.yml"


def test_session_submit_uses_module_session_target(monkeypatch):
    console = Console(record=True, width=120)
    submitted: list[tuple[str, dict]] = []

    class BrokenTarget:
        LOCAL = SimpleNamespace(value="broken-local")
        CLOUD = SimpleNamespace(value="broken-cloud")

    fake_target = SimpleNamespace(
        LOCAL=SimpleNamespace(value="module-local"),
        CLOUD=SimpleNamespace(value="module-cloud"),
    )

    monkeypatch.setattr(session_app_module, "get_console", lambda: console)
    monkeypatch.setattr(session_app_module, "get_cli_env_vars", lambda: {}, raising=False)
    monkeypatch.setattr(session_app_module, "get_cli_project", lambda: "", raising=False)
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "print_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_app_module, "_session_detail_table", lambda _session: "details")
    monkeypatch.setattr(session_app_module, "ProjectManager", SimpleNamespace(get_active_path=lambda: None), raising=False)
    monkeypatch.setattr(session_app_module, "SessionManager", lambda: _SubmitManager(submitted), raising=False)
    monkeypatch.setattr(session_app_module, "SessionTarget", fake_target, raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionTarget", BrokenTarget)

    result = runner.invoke(app, ["submit", "scan.yml", "--cloud", "demo-profile"])

    assert result.exit_code == 0
    assert submitted[0][1]["target"].value == "module-cloud"


def test_session_list_uses_module_session_store_and_status(monkeypatch):
    console = Console(record=True, width=120)
    sessions = [
        SimpleNamespace(
            id="sess-1",
            name="demo",
            project="proj",
            target=SimpleNamespace(value="local"),
            status=SimpleNamespace(value="completed"),
            workflow_file="scan.yml",
            instance_ip="",
            remote_pid=None,
            age_display=lambda: "1h",
        )
    ]

    class BrokenStore:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionStore")

    monkeypatch.setattr(session_app_module, "get_console", lambda: console)
    monkeypatch.setattr(session_app_module, "SessionStore", lambda: _SessionStoreStub(sessions), raising=False)
    monkeypatch.setattr(session_app_module, "SessionStatus", _FakeSessionStatus, raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionStore", BrokenStore)

    result = runner.invoke(app, ["list", "--status", "completed"])

    assert result.exit_code == 0
    assert "sess-1" in console.export_text()


def test_session_guard_uses_module_status_binding(monkeypatch):
    calls: list[tuple[int | None, object]] = []

    class BrokenStatus:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.models.SessionStatus")

    class FakeStore:
        def clean(self, *, older_than_seconds=None, statuses=None):
            calls.append((older_than_seconds, statuses))
            return 1

    monkeypatch.setattr(session_app_module, "SessionStore", lambda: FakeStore(), raising=False)
    monkeypatch.setattr(session_app_module, "SessionStatus", _FakeSessionStatus, raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.models.SessionStatus", BrokenStatus)
    monkeypatch.setattr(session_app_module, "print_success", lambda *args, **kwargs: None)

    result = runner.invoke(app, ["guard", "--older-than", "2h", "--status", "completed"])

    assert result.exit_code == 0
    assert calls == [(7200, [_FakeSessionStatus.COMPLETED])]


def test_session_list_invalid_status_shows_valid_values(monkeypatch):
    console = Console(record=True, width=120)

    class _StatusMeta(type):
        def __iter__(cls):
            return iter([SimpleNamespace(value="completed"), SimpleNamespace(value="failed")])

    class AlwaysBadStatus(metaclass=_StatusMeta):
        def __init__(self, value):
            raise ValueError(value)

    monkeypatch.setattr(session_app_module, "get_console", lambda: console)
    monkeypatch.setattr(session_app_module, "SessionStore", lambda: _SessionStoreStub(), raising=False)
    monkeypatch.setattr(session_app_module, "SessionStatus", AlwaysBadStatus, raising=False)

    result = runner.invoke(app, ["list", "--status", "bogus"])

    assert result.exit_code == 1
    output = console.export_text()
    assert "Unknown status: bogus" in output
    assert "Valid: completed, failed" in output


def test_session_list_no_sessions_prints_info(monkeypatch):
    infos: list[tuple[str, str]] = []

    monkeypatch.setattr(session_app_module, "get_console", lambda: SimpleNamespace(print=lambda *a, **k: None))
    monkeypatch.setattr(session_app_module, "SessionStore", lambda: _SessionStoreStub([]), raising=False)
    monkeypatch.setattr(session_app_module, "print_info", lambda title, msg, **kwargs: infos.append((title, msg)))

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert infos == [("Sessions", "No sessions found.")]


def test_session_clean_no_matches_prints_info(monkeypatch):
    infos: list[tuple[str, str]] = []

    class FakeStore:
        def list_sessions(self):
            return []

        def clean(self, *, older_than_seconds=None, statuses=None):
            return 0

    monkeypatch.setattr(session_app_module, "get_console", lambda: SimpleNamespace(print=lambda *a, **k: None))
    monkeypatch.setattr(session_app_module, "SessionStore", lambda: FakeStore(), raising=False)
    monkeypatch.setattr(session_app_module, "SessionStatus", _FakeSessionStatus, raising=False)
    monkeypatch.setattr(session_app_module, "print_info", lambda title, msg, **kwargs: infos.append((title, msg)))

    result = runner.invoke(app, ["clean", "--status", "completed", "--yes"])

    assert result.exit_code == 0
    assert infos == [("Sessions", "No sessions match the criteria.")]


def test_session_bundle_reports_result_path(monkeypatch, tmp_path):
    successes: list[tuple[str, str, dict | None]] = []

    class FakeManager:
        async def bundle_artifacts(self, session_id, output_file=None):
            return tmp_path / "bundle.tar.gz"

    monkeypatch.setattr(session_app_module, "print_success", lambda title, msg, details=None: successes.append((title, msg, details)))
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", lambda: FakeManager())

    result = runner.invoke(app, ["bundle", "sess-1", "--output", str(tmp_path / "out.tar.gz")])

    assert result.exit_code == 0
    assert successes == [
        ("Bundle created", "Run artifacts bundle created.", {"Path": str(tmp_path / "bundle.tar.gz")})
    ]


def test_session_bundle_uses_module_session_manager(monkeypatch, tmp_path):
    successes: list[tuple[str, str, dict | None]] = []
    bundle_calls: list[tuple[str, Path | None]] = []

    class BrokenManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("should not use ofx.cloud.sessions.SessionManager")

    class FakeManager:
        async def bundle_artifacts(self, session_id, output_file=None):
            bundle_calls.append((session_id, output_file))
            return tmp_path / "bundle.tar.gz"

    monkeypatch.setattr(session_app_module, "print_success", lambda title, msg, details=None: successes.append((title, msg, details)))
    monkeypatch.setattr(session_app_module, "SessionManager", lambda: FakeManager(), raising=False)
    monkeypatch.setattr("ofx.cloud.sessions.SessionManager", BrokenManager)

    out_path = tmp_path / "out.tar.gz"
    result = runner.invoke(app, ["bundle", "sess-1", "--output", str(out_path)])

    assert result.exit_code == 0
    assert bundle_calls == [("sess-1", out_path)]
    assert successes == [
        ("Bundle created", "Run artifacts bundle created.", {"Path": str(tmp_path / "bundle.tar.gz")})
    ]


def test_session_clean_abort_prints_info(monkeypatch):
    infos: list[tuple[str, str]] = []

    class FakeStore:
        def list_sessions(self):
            return [
                SimpleNamespace(
                    id="sess-1",
                    name="demo",
                    status=SimpleNamespace(value="completed"),
                    started_at=datetime.now(UTC) - timedelta(hours=2),
                    age_display=lambda: "2h",
                )
            ]

        def clean(self, *, older_than_seconds=None, statuses=None):
            return 1

    monkeypatch.setattr(session_app_module, "get_console", lambda: SimpleNamespace(print=lambda *a, **k: None))
    monkeypatch.setattr(session_app_module, "SessionStore", lambda: FakeStore(), raising=False)
    monkeypatch.setattr(session_app_module, "SessionStatus", _FakeSessionStatus, raising=False)
    monkeypatch.setattr(session_app_module, "print_info", lambda title, msg, **kwargs: infos.append((title, msg)))
    monkeypatch.setattr("typer.confirm", lambda _msg: False)

    result = runner.invoke(app, ["clean", "--status", "completed"])

    assert result.exit_code == 0
    assert infos[-1] == ("Clean", "Aborted.")
