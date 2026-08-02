"""Tests for the detached sessions feature (models, store, script builder, encryption, manager)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tarfile
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

import ofx.settings as _settings_mod
from ofx.cloud.sessions.encryption import decrypt_results, derive_key, encrypt_results
from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.cloud.sessions.store import SessionStore
from ofx.models.step import Step


@pytest.fixture(autouse=True)
def _restore_workflow_dirs():
    original = list(_settings_mod.DEFAULT_WORKFLOWS_DIRS)
    yield
    _settings_mod.DEFAULT_WORKFLOWS_DIRS = original

class TestSessionModel:
    def test_create_minimal(self):
        s = Session(id="aabbccdd", workflow_file="scan.yml")
        assert s.id == "aabbccdd"
        assert s.target == SessionTarget.LOCAL
        assert s.status == SessionStatus.PROVISIONING
        assert s.is_running()
        assert not s.is_done()

    def test_is_running_states(self):
        for status in (
            SessionStatus.PROVISIONING,
            SessionStatus.UPLOADING,
            SessionStatus.RUNNING,
        ):
            s = Session(id="test", workflow_file="w.yml", status=status)
            assert s.is_running(), f"{status} should be running"

    def test_is_done_states(self):
        for status in (
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELED,
            SessionStatus.FETCHED,
            SessionStatus.ENCRYPTED,
            SessionStatus.DESTROYED,
            SessionStatus.UNREACHABLE,
        ):
            s = Session(id="test", workflow_file="w.yml", status=status)
            assert s.is_done(), f"{status} should be done"
            assert not s.is_running(), f"{status} should not be running"

    def test_age_display(self):
        s = Session(
            id="test",
            workflow_file="w.yml",
            started_at=datetime.now(UTC) - timedelta(hours=2, minutes=30),
        )
        age = s.age_display()
        assert "2h" in age

    def test_cloud_session(self):
        s = Session(
            id="test",
            workflow_file="w.yml",
            target=SessionTarget.CLOUD,
            cloud_profile="do-nyc",
            instance_ip="1.2.3.4",
            instance_id="inst-123",
        )
        assert s.target == SessionTarget.CLOUD
        assert s.instance_ip == "1.2.3.4"

    def test_extra_fields_allowed(self):
        s = Session(id="test", workflow_file="w.yml", custom_field="hello")
        assert s.custom_field == "hello"

class TestSessionStore:
    def test_save_and_load(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        session = Session(id="abc12345", workflow_file="test.yml", name="my-scan")
        store.save(session)

        loaded = store.load("abc12345")
        assert loaded.id == "abc12345"
        assert loaded.name == "my-scan"
        assert loaded.workflow_file == "test.yml"

    def test_load_not_found(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent")

    def test_exists(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        assert not store.exists("abc12345")
        store.save(Session(id="abc12345", workflow_file="w.yml"))
        assert store.exists("abc12345")

    def test_delete(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        store.save(Session(id="abc12345", workflow_file="w.yml"))
        assert store.exists("abc12345")
        store.delete("abc12345")
        assert not store.exists("abc12345")

    def test_update_status(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        store.save(
            Session(id="abc12345", workflow_file="w.yml", status=SessionStatus.RUNNING)
        )
        updated = store.update_status("abc12345", SessionStatus.COMPLETED)
        assert updated.status == SessionStatus.COMPLETED

    def test_update_status_preserves_fields(self, tmp_path):
        """Atomic update must preserve fields not being updated."""
        store = SessionStore(base_dir=tmp_path / "sessions")
        store.save(
            Session(
                id="abc12345",
                workflow_file="w.yml",
                status=SessionStatus.RUNNING,
                project="myproject",
            )
        )
        updated = store.update_status(
            "abc12345", SessionStatus.COMPLETED, error="test error"
        )
        assert updated.status == SessionStatus.COMPLETED
        assert updated.project == "myproject"
        assert updated.error == "test error"
        reloaded = store.load("abc12345")
        assert reloaded.status == SessionStatus.COMPLETED
        assert reloaded.project == "myproject"

    def test_update_status_missing_session(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        with pytest.raises(FileNotFoundError):
            store.update_status("nonexistent", SessionStatus.COMPLETED)

    def test_list_sessions(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        store.save(
            Session(id="aaa", workflow_file="w1.yml", status=SessionStatus.RUNNING)
        )
        store.save(
            Session(id="bbb", workflow_file="w2.yml", status=SessionStatus.COMPLETED)
        )
        store.save(
            Session(
                id="ccc",
                workflow_file="w3.yml",
                status=SessionStatus.RUNNING,
                target=SessionTarget.CLOUD,
            )
        )

        all_sessions = store.list_sessions()
        assert len(all_sessions) == 3

        running = store.list_sessions(status=SessionStatus.RUNNING)
        assert len(running) == 2

        cloud = store.list_sessions(target="cloud")
        assert len(cloud) == 1
        assert cloud[0].id == "ccc"

    def test_list_sessions_skips_corrupt_metadata(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        store.save(Session(id="good", workflow_file="w.yml"))
        bad_dir = tmp_path / "sessions" / "bad"
        bad_dir.mkdir(parents=True)
        (bad_dir / "session.json").write_text("{not-json")

        sessions = store.list_sessions()

        assert [session.id for session in sessions] == ["good"]

    def test_results_dir(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        store.save(Session(id="abc12345", workflow_file="w.yml"))
        results = store.results_dir("abc12345")
        assert results.exists()
        assert results.name == "results"

    def test_clean(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        old_time = datetime.now(UTC) - timedelta(days=10)
        store.save(
            Session(
                id="old",
                workflow_file="w.yml",
                status=SessionStatus.COMPLETED,
                started_at=old_time,
            )
        )
        store.save(
            Session(
                id="new",
                workflow_file="w.yml",
                status=SessionStatus.COMPLETED,
            )
        )

        removed = store.clean(
            older_than_seconds=7 * 86400, statuses=[SessionStatus.COMPLETED]
        )
        assert removed == 1
        assert not store.exists("old")
        assert store.exists("new")

    def test_session_dir_path(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        d = store.session_dir("myid")
        assert d == tmp_path / "sessions" / "myid"

class TestScriptBuilder:
    def _make_step(self, **kwargs):
        """Create a minimal Step-like object."""
        from ofx.models.step import Step

        return Step(**kwargs)

    def test_bash_single_command(self):
        steps = [self._make_step(name="recon", run="nmap -sV 10.0.0.1")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="/tmp/test",
            workflow_name="wf-one",
            job_name="recon-job",
        )
        assert "#!/bin/bash" in script
        assert "SESSION_ID" in script
        assert "nmap -sV 10.0.0.1" in script
        assert "__TASK_OK__" in script
        assert "__TASK_ERR__" in script
        assert "workflow=wf-one job=recon-job" in script

    def test_bash_multiple_steps(self):
        steps = [
            self._make_step(name="step1", run="echo hello"),
            self._make_step(name="step2", run="echo world"),
        ]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert "step1 [command]" in script
        assert "step2 [command]" in script
        assert script.count(">>> Step") == 2

    def test_bash_log_descriptor_includes_run_type(self):
        steps = [self._make_step(name="py-inline", script='print("ok")')]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert "py-inline [script]" in script
        assert "FAILED" in script

    def test_bash_env_vars(self):
        steps = [self._make_step(run="env")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="/tmp/test",
            env={"TARGET": "10.0.0.1", "PORT": "443"},
        )
        assert "export TARGET=" in script
        assert "export PORT=" in script

    def test_bash_env_vars_skip_reserved_keys(self):
        steps = [self._make_step(run="env")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="/tmp/test",
            env={"PATH": "/tmp/custom", "TARGET": "10.0.0.1"},
        )
        assert "export TARGET=" in script
        assert 'export PATH="/tmp/custom"' not in script

    def test_invalid_env_var_name_raises(self):
        steps = [self._make_step(run="env")]
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            build_session_script(
                steps,
                session_id="aabb",
                work_dir="/tmp/test",
                env={"BAD-NAME": "oops"},
            )

    def test_bash_continue_on_error(self):
        steps = [self._make_step(run="might-fail", continue_on_error=True)]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert "continue_on_error" in script

    def test_bash_inline_script(self):
        steps = [self._make_step(name="inline", script="echo hello\necho world")]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert '"$__OFX_PY_BIN" ".ofx_step_0.py"' in script

    def test_powershell_basic(self):
        steps = [self._make_step(name="wincheck", run="Get-Process")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="C:\\Windows\\Temp\\test",
            workflow_name="wf-win",
            job_name="win-job",
            os_type="windows",
        )
        assert "$ErrorActionPreference" in script
        assert "SESSION_ID" in script
        assert "Get-Process" in script
        assert "wincheck [command]" in script
        assert "workflow=wf-win job=win-job" in script
        assert "__TASK_OK__" in script

    def test_script_file_step(self):
        steps = [self._make_step(name="sf", script_file="/opt/scripts/scan.sh")]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert '"$__OFX_PY_BIN" ".ofx_step_0.py"' in script

    def test_bash_encrypt_at_rest(self):
        steps = [self._make_step(name="scan", run="echo hi")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="/tmp/test",
            encrypt_at_rest=True,
        )
        assert ".skey" in script
        assert "openssl enc" in script
        assert "output.enc" in script
        assert "shred" in script
        assert "__TASK_OK__" in script

    def test_bash_encrypt_failure_is_fatal(self):
        """Encryption failure must abort the script, not leave data unencrypted."""
        steps = [self._make_step(name="scan", run="echo hi")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="/tmp/test",
            encrypt_at_rest=True,
        )
        assert "FATAL" in script
        assert "__TASK_ERR__" in script
        assert "output left unencrypted" not in script

    def test_bash_no_encrypt_by_default(self):
        steps = [self._make_step(name="scan", run="echo hi")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="/tmp/test",
            encrypt_at_rest=False,
        )
        assert "openssl enc" not in script
        assert "__TASK_OK__" in script

    def test_powershell_encrypt_at_rest(self):
        steps = [self._make_step(name="scan", run="Get-Process")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="C:\\Temp\\test",
            os_type="windows",
            encrypt_at_rest=True,
        )
        assert ".skey" in script
        assert "output.enc" in script
        assert "AES" in script or "Aes" in script

    def test_powershell_encrypt_failure_is_fatal(self):
        """PowerShell encryption failure must abort, not leave data unencrypted."""
        steps = [self._make_step(name="scan", run="Get-Process")]
        script = build_session_script(
            steps,
            session_id="aabb",
            work_dir="C:\\Temp\\test",
            os_type="windows",
            encrypt_at_rest=True,
        )
        assert "FATAL" in script
        assert "__TASK_ERR__" in script

class TestEncryption:
    def test_derive_key_deterministic(self):
        salt = b"test_salt_123456"
        key1, s1 = derive_key("mysecret", salt=salt)
        key2, s2 = derive_key("mysecret", salt=salt)
        assert key1 == key2
        assert s1 == s2

    def test_derive_key_different_passphrase(self):
        salt = b"test_salt_123456"
        key1, _ = derive_key("pass1", salt=salt)
        key2, _ = derive_key("pass2", salt=salt)
        assert key1 != key2

    def test_derive_key_random_salt(self):
        key1, salt1 = derive_key("same")
        key2, salt2 = derive_key("same")
        assert salt1 != salt2
        assert key1 != key2

    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        results = tmp_path / "results"
        results.mkdir()
        (results / "output.txt").write_text("scan results here")
        (results / "nmap.xml").write_text("<nmap>data</nmap>")

        enc_file = encrypt_results(results, "hunter2")
        assert enc_file.exists()
        assert enc_file.name == "results.enc"
        assert enc_file.stat().st_size > 0

        out = tmp_path / "decrypted"
        decrypt_results(enc_file, "hunter2", out)
        assert (out / "results" / "output.txt").exists()
        assert (out / "results" / "output.txt").read_text() == "scan results here"
        assert (out / "results" / "nmap.xml").read_text() == "<nmap>data</nmap>"

    def test_decrypt_wrong_passphrase(self, tmp_path):
        results = tmp_path / "results"
        results.mkdir()
        (results / "data.txt").write_text("secret")

        enc_file = encrypt_results(results, "correct")

        with pytest.raises(ValueError, match="wrong passphrase"):
            decrypt_results(enc_file, "wrong", tmp_path / "out")

    def test_encrypt_empty_dir_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="No files"):
            encrypt_results(empty, "pass")

    def test_encrypt_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            encrypt_results(tmp_path / "nonexistent", "pass")

    def test_decrypt_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            decrypt_results(tmp_path / "nope.enc", "pass")

    def test_custom_output_file(self, tmp_path):
        results = tmp_path / "results"
        results.mkdir()
        (results / "data.txt").write_text("content")

        custom = tmp_path / "custom.enc"
        out = encrypt_results(results, "pass", output_file=custom)
        assert out == custom
        assert custom.exists()

class TestSessionManagerLocal:
    """Tests for local session submission and lifecycle.

    These tests use real subprocesses but no SSH/cloud — fully local.
    """

    def _create_test_workflow(self, tmp_path: Path) -> Path:
        """Write a minimal workflow YAML that echoes output."""
        wf = tmp_path / "test_session.yml"
        wf.write_text(
            textwrap.dedent("""\
            name: session-test
            jobs:
              echo-job:
                steps:
                  - name: greet
                    run: echo "Hello from session"
                  - name: write-output
                    run: echo "result data" > output/result.txt
        """)
        )
        return wf

    def _create_multi_job_workflow(self, tmp_path: Path) -> Path:
        """Write a two-job workflow to validate full-workflow session submit."""
        wf = tmp_path / "test_session_multi.yml"
        wf.write_text(
            textwrap.dedent("""\
            name: session-multi
            jobs:
              first-job:
                steps:
                  - name: first
                    run: echo "FIRST_JOB" >> output/trace.txt
              second-job:
                needs: [first-job]
                steps:
                  - name: second
                    run: echo "SECOND_JOB" >> output/trace.txt
        """)
        )
        return wf

    def test_submit_local_creates_session(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(
                str(wf_path),
                target=SessionTarget.LOCAL,
                name="test-local",
            )
        )

        assert session.id
        assert session.target == SessionTarget.LOCAL
        assert session.status == SessionStatus.RUNNING
        assert session.remote_pid is not None
        assert session.name == "test-local"

        assert session.at_rest_key
        assert len(session.at_rest_key) == 64
        assert session.at_rest_encrypted

        loaded = store.load(session.id)
        assert loaded.id == session.id
        assert loaded.at_rest_key == session.at_rest_key

    def test_submit_local_runs_script(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))

        import time

        for _ in range(50):
            time.sleep(0.1)
            try:
                os.kill(session.remote_pid, 0)
            except ProcessLookupError:
                break

        session = asyncio.run(mgr.status(session.id))
        assert session.status == SessionStatus.COMPLETED

        work = Path(session.remote_work_dir)
        assert (work / "output.enc").exists(), (
            "output.enc missing — at-rest encryption failed"
        )
        assert not (work / "output").exists(), (
            "output/ dir should be removed after encryption"
        )
        assert not (work / ".skey").exists(), "key file should be shredded"

    def test_submit_local_runs_full_workflow_by_default(self, tmp_path):
        wf_path = self._create_multi_job_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))
        assert session.job_id == ""

        import time

        for _ in range(60):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        assert session.status == SessionStatus.COMPLETED
        results_path = asyncio.run(mgr.fetch(session.id))
        trace = (results_path / "trace.txt").read_text()
        assert "FIRST_JOB" in trace
        assert "SECOND_JOB" in trace

    def test_submit_local_job_override_runs_only_selected_job(self, tmp_path):
        wf_path = self._create_multi_job_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL, job_id="second-job")
        )
        assert session.job_id == "second-job"

        import time

        for _ in range(60):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        assert session.status == SessionStatus.COMPLETED
        results_path = asyncio.run(mgr.fetch(session.id))
        trace = (results_path / "trace.txt").read_text()
        assert "FIRST_JOB" not in trace
        assert "SECOND_JOB" in trace

    def test_submit_local_stages_bundled_python_script(self, tmp_path):
        wf = tmp_path / "test_script_session.yml"
        wf.write_text(
            textwrap.dedent("""\
            name: session-script-test
            jobs:
              py-job:
                steps:
                  - name: inline-python
                    script: |
                      print("INLINE_SCRIPT_OK")
        """)
        )
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)
        session = asyncio.run(mgr.submit(str(wf), target=SessionTarget.LOCAL))
        bundled = Path(session.remote_work_dir) / ".ofx_step_0.py"
        assert bundled.exists()
        bundled_text = bundled.read_text()
        assert "INLINE_SCRIPT_OK" not in bundled_text
        assert "_m.loads" in bundled_text or "base64.b64decode" in bundled_text

    def test_submit_local_rejects_profile_time_window_outside_allowed_range(self, tmp_path, monkeypatch):
        from ofx.profiles.models import OFXProfile, TimeWindow

        wf_path = self._create_test_workflow(tmp_path)
        wf_data = yaml.safe_load(wf_path.read_text())
        wf_data["defaults"] = {"profile": "stealth"}
        wf_path.write_text(yaml.safe_dump(wf_data))

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)
        profile = OFXProfile(
            name="stealth",
            time_window=TimeWindow(enabled=True, start="09:00", end="17:00"),
        )

        monkeypatch.setattr(
            "ofx.profiles.manager.get_profile_manager",
            lambda: SimpleNamespace(resolve_or_default=lambda _name: profile),
        )
        monkeypatch.setattr(
            "ofx.profiles.time_window.check_time_window",
            lambda _window: {
                "allowed": False,
                "remaining_minutes": 0,
                "message": "Current time 22:00 UTC is outside the allowed window",
            },
        )

        with pytest.raises(RuntimeError, match="outside the allowed window"):
            asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))

        assert store.list_sessions() == []

    def test_status_completed(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))

        import time

        for _ in range(50):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        assert session.status == SessionStatus.COMPLETED

    def test_logs_returns_output(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))

        import time

        for _ in range(50):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        logs = asyncio.run(mgr.logs(session.id))
        assert "Session" in logs or "started" in logs

    def test_check_local_status_alive_without_marker_stays_running(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)
        session = Session(
            id="localrun1",
            workflow_file="wf.yml",
            target=SessionTarget.LOCAL,
            status=SessionStatus.RUNNING,
            remote_pid=1234,
            remote_log_file=str(tmp_path / "output.log"),
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("os.kill", lambda pid, sig: None)
            mp.setattr("builtins.open", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
            mp.setattr("pathlib.Path.exists", lambda self: False)
            result = mgr._check_local_status(session)

        assert result.status == SessionStatus.RUNNING

    def test_check_local_status_exited_without_marker_fails(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)
        session = Session(
            id="localrun2",
            workflow_file="wf.yml",
            target=SessionTarget.LOCAL,
            status=SessionStatus.RUNNING,
            remote_pid=1234,
            remote_log_file=str(tmp_path / "output.log"),
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "os.kill",
                lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()),
            )
            mp.setattr("pathlib.Path.exists", lambda self: False)
            result = mgr._check_local_status(session)

        assert result.status == SessionStatus.FAILED
        assert result.error == "Process exited without success marker"

    def test_fetch_results(self, tmp_path):
        """Fetch transparently decrypts at-rest encrypted output."""
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))

        import time

        for _ in range(50):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        assert session.status == SessionStatus.COMPLETED

        results_path = asyncio.run(mgr.fetch(session.id))
        assert results_path.exists()

        assert (results_path / "result.txt").exists(), (
            f"result.txt missing; contents: {list(results_path.iterdir())}"
        )

        session = store.load(session.id)
        assert session.status == SessionStatus.FETCHED

    def test_fetch_with_encryption(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))

        import time

        for _ in range(50):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        enc_path = asyncio.run(mgr.fetch(session.id, passphrase="s3cret"))
        assert enc_path.exists()
        assert enc_path.suffix == ".enc"

        session = store.load(session.id)
        assert session.status == SessionStatus.ENCRYPTED
        assert session.encrypted

    def test_cancel_running(self, tmp_path):
        """Submit a long-running job and cancel it."""
        wf = tmp_path / "long_running.yml"
        wf.write_text(
            textwrap.dedent("""\
            name: long-run
            jobs:
              wait-job:
                steps:
                  - name: wait
                    run: sleep 30
        """)
        )
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf), target=SessionTarget.LOCAL))
        assert session.remote_pid is not None

        import time

        time.sleep(0.2)
        session = asyncio.run(mgr.cancel(session.id))
        assert session.status == SessionStatus.CANCELED

        time.sleep(0.2)
        try:
            os.kill(session.remote_pid, 0)
        except ProcessLookupError:
            pass

    def test_destroy_local_cleans_workspace(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))
        work_dir = Path(session.remote_work_dir)

        import time

        for _ in range(50):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        assert work_dir.exists()

        session = asyncio.run(mgr.destroy(session.id))

        assert session.status == SessionStatus.DESTROYED
        assert not work_dir.exists()
        assert store.load(session.id).status == SessionStatus.DESTROYED

    def test_bundle_artifacts_creates_tar(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))
        import time

        for _ in range(50):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        asyncio.run(mgr.fetch(session.id))
        bundle = asyncio.run(mgr.bundle_artifacts(session.id))
        assert bundle.exists()
        assert bundle.suffixes[-2:] == [".tar", ".gz"]

    def test_bundle_manifest_marks_full_workflow_scope(self, tmp_path):
        wf_path = self._create_multi_job_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf_path), target=SessionTarget.LOCAL))
        import time

        for _ in range(60):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        asyncio.run(mgr.fetch(session.id))
        bundle = asyncio.run(mgr.bundle_artifacts(session.id))
        with tarfile.open(bundle, "r:gz") as tf:
            manifest = json.loads(
                tf.extractfile("manifest.json").read().decode("utf-8")
            )

        assert manifest["job_id"] == ""
        assert manifest["execution_scope"] == "full-workflow"

    def test_bundle_manifest_marks_single_job_scope(self, tmp_path):
        wf_path = self._create_multi_job_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL, job_id="second-job")
        )
        import time

        for _ in range(60):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        asyncio.run(mgr.fetch(session.id))
        bundle = asyncio.run(mgr.bundle_artifacts(session.id))
        with tarfile.open(bundle, "r:gz") as tf:
            manifest = json.loads(
                tf.extractfile("manifest.json").read().decode("utf-8")
            )

        assert manifest["job_id"] == "second-job"
        assert manifest["execution_scope"] == "second-job"

    def test_bundle_artifacts_includes_project_logs(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)

        project_path = tmp_path / "project"
        logs_dir = project_path / "logs"
        logs_dir.mkdir(parents=True)
        (logs_dir / "scan.log").write_text("project log")

        results_dir = store.results_dir("projbundle")
        (results_dir / "result.txt").write_text("result")

        session = Session(
            id="projbundle",
            workflow_file="wf.yml",
            status=SessionStatus.FETCHED,
            project="demo-project",
            results_path=str(results_dir),
        )
        store.save(session)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "ofx.commands.project.project_manager.ProjectManager.resolve_path",
                lambda name: str(project_path),
            )
            bundle = asyncio.run(mgr.bundle_artifacts(session.id))

        with tarfile.open(bundle, "r:gz") as tf:
            names = tf.getnames()

        assert "project_logs/scan.log" in names

    def test_resolve_results_dir_uses_project_evidence_path(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        project_path = tmp_path / "project"
        project_path.mkdir()
        session = Session(
            id="projresults",
            workflow_file="wf.yml",
            project="demo-project",
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "ofx.commands.project.project_manager.ProjectManager.resolve_path",
                lambda name: str(project_path),
            )
            results_dir = mgr._resolve_results_dir(session)

        assert results_dir == project_path / "evidence" / "sessions" / "projresults"
        assert results_dir.exists()

    def test_fetch_while_running_raises(self, tmp_path):
        wf = tmp_path / "long_running.yml"
        wf.write_text(
            textwrap.dedent("""\
            name: long-run
            jobs:
              wait-job:
                steps:
                  - name: wait
                    run: sleep 30
        """)
        )
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(mgr.submit(str(wf), target=SessionTarget.LOCAL))

        with pytest.raises(RuntimeError, match="still running"):
            asyncio.run(mgr.fetch(session.id))

        asyncio.run(mgr.cancel(session.id))

class TestSessionManagerDecrypt:
    def test_decrypt_after_encrypted_fetch(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        session_dir = tmp_path / "sessions" / "testid"
        results_dir = session_dir / "results"
        results_dir.mkdir(parents=True)
        (results_dir / "data.txt").write_text("secret stuff")

        enc_file = encrypt_results(results_dir, "mypass")

        session = Session(
            id="testid",
            workflow_file="w.yml",
            status=SessionStatus.ENCRYPTED,
            encrypted=True,
            encrypted_file=str(enc_file),
        )
        store.save(session)

        from ofx.cloud.sessions import SessionManager

        mgr = SessionManager(store=store)
        out = asyncio.run(mgr.decrypt("testid", "mypass"))
        assert out.exists()
        assert (out / "results" / "data.txt").exists()

class TestSessionInputInjection:
    """Tests for session input → env var injection and local file staging."""

    def test_local_submit_injects_env(self, tmp_path):
        """Local session script contains INPUT_ env vars for workflow inputs."""
        import ofx.settings as settings_mod

        original_dirs = list(settings_mod.DEFAULT_WORKFLOWS_DIRS)

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        wf_file = tmp_path / "scan.yml"
        wf_file.write_text(
            "name: scan\njobs:\n  scan:\n    steps:\n      - run: echo $INPUT_MODE\n"
        )

        try:
            session = asyncio.run(
                mgr.submit(
                    str(wf_file),
                    inputs={"mode": "fast"},
                    name="test-inject",
                )
            )

            script = (Path(session.remote_work_dir) / "run.sh").read_text()
            assert 'export INPUT_MODE="fast"' in script
            assert 'export mode="fast"' in script

            asyncio.run(mgr.cancel(session.id))
        finally:
            settings_mod.DEFAULT_WORKFLOWS_DIRS = original_dirs

    def test_local_submit_stages_file_input(self, tmp_path):
        """Local session copies file-valued inputs into the session workspace."""
        import ofx.settings as settings_mod

        original_dirs = list(settings_mod.DEFAULT_WORKFLOWS_DIRS)

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        targets = tmp_path / "targets.txt"
        targets.write_text("10.0.0.1\n10.0.0.2\n")

        wf_file = tmp_path / "scan.yml"
        wf_file.write_text(
            "name: scan\njobs:\n  scan:\n    steps:\n      - run: cat $INPUT_TARGETS_FILE\n"
        )

        try:
            session = asyncio.run(
                mgr.submit(
                    str(wf_file),
                    inputs={"targets_file": str(targets)},
                    name="test-file-stage",
                )
            )

            work_dir = Path(session.remote_work_dir)
            staged = work_dir / targets.name
            assert staged.exists()
            script = (work_dir / "run.sh").read_text()
            assert str(staged) in script

            asyncio.run(mgr.cancel(session.id))
        finally:
            settings_mod.DEFAULT_WORKFLOWS_DIRS = original_dirs

    def test_local_submit_stage_file_failure_raises(self, tmp_path):
        """Local submit should fail fast when staging a file input fails."""
        import ofx.settings as settings_mod

        original_dirs = list(settings_mod.DEFAULT_WORKFLOWS_DIRS)

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        targets = tmp_path / "targets.txt"
        targets.write_text("10.0.0.1\n")

        wf_file = tmp_path / "scan.yml"
        wf_file.write_text(
            "name: scan\njobs:\n  scan:\n    steps:\n      - run: cat $INPUT_TARGETS_FILE\n"
        )

        real_copy2 = shutil.copy2

        def _copy2_fail(src, dst, *args, **kwargs):
            if str(src) == str(targets):
                raise OSError("copy failed")
            return real_copy2(src, dst, *args, **kwargs)

        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(shutil, "copy2", _copy2_fail)
                with pytest.raises(
                    RuntimeError, match="Failed to stage session input file"
                ):
                    asyncio.run(
                        mgr.submit(
                            str(wf_file),
                            inputs={"targets_file": str(targets)},
                            name="test-file-stage-fail",
                        )
                    )
        finally:
            settings_mod.DEFAULT_WORKFLOWS_DIRS = original_dirs

    def test_start_cloud_remote_submit_raises_on_input_upload_failure(self, tmp_path):
        """Cloud submit startup must fail fast on upload errors."""
        from types import SimpleNamespace

        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        src = tmp_path / "hosts.txt"
        src.write_text("10.0.0.1\n")
        session = Session(
            id="cloudscriptfail",
            workflow_file="wf.yml",
            inputs={"targets_file": str(src)},
        )
        target = SimpleNamespace(
            resolved="resolved-config",
            instance=SimpleNamespace(ip="10.0.0.8"),
            os_type="linux",
            is_windows=False,
        )
        runtime = SimpleNamespace(
            session=session,
            remote_work_dir="/tmp/.ses-1",
            at_rest_key="key123",
            remote_log="/tmp/.ses-1/output.log",
            sep="/",
            merged_env={},
        )

        remote = SimpleNamespace(
            upload=lambda local_path, remote_path: (_ for _ in ()).throw(
                RuntimeError("upload broke")
            ),
            run=lambda *args, **kwargs: "",
            cleanup=lambda: None,
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("ofx.cloud.runtime.create_remote_runner", lambda *_args, **_kwargs: remote)
            with pytest.raises(RuntimeError, match="Failed to upload session input file"):
                mgr._start_cloud_remote_submit(
                    [Step(run="echo ok")],
                    target=target,
                    runtime=runtime,
                    workflow_dir=None,
                    workflow_name="wf-name",
                )

class TestSessionSubmitHelpers:
    def test_resolved_cloud_submit_state_normalizes_connection_defaults(self):
        from types import SimpleNamespace

        from ofx.cloud.sessions import SessionManager

        resolved = SimpleNamespace(os="windows")
        state = SessionManager._resolved_cloud_submit_state(resolved)

        assert state.os_type == "windows"
        assert state.is_windows is True
        assert state.session_update["ssh_user"] == "root"
        assert state.session_update["winrm_user"] == "Administrator"
        assert state.session_update["winrm_port"] == 5985

    def test_reconnect_uses_normalized_connection_defaults(self):
        from ofx.cloud.sessions import SessionManager

        session = Session(
            id="cfg12345",
            workflow_file="wf.yml",
            instance_ip="10.0.0.9",
            os_type="windows",
            ssh_user="svc-user",
            ssh_password="secret",
            winrm_user="",
            winrm_ssl=True,
            winrm_port=5986,
        )
        manager = SessionManager()
        seen: list[tuple[object, str, int]] = []

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "ofx.cloud.runtime.create_remote_runner",
                lambda cfg, host, max_retries=0: seen.append((cfg, host, max_retries)) or "remote",
            )
            remote = manager._reconnect(session)

        cfg, host, max_retries = seen[0]
        assert remote == "remote"
        assert cfg.connection_type == "winrm"
        assert cfg.ssh_user == "svc-user"
        assert cfg.winrm_user == "svc-user"
        assert cfg.winrm_password == "secret"
        assert cfg.winrm_port == 5986
        assert host == "10.0.0.9"
        assert max_retries == 2

    def test_resolved_cloud_submit_state_reuses_normalized_connection_values(self):
        from types import SimpleNamespace

        from ofx.cloud.sessions import SessionManager

        resolved = SimpleNamespace(provider="static", os="windows", winrm_ssl=True)

        state = SessionManager._resolved_cloud_submit_state(resolved)

        assert state.os_type == "windows"
        assert state.is_windows is True
        assert state.session_update["cloud_provider"] == "static"
        assert state.session_update["os_type"] == "windows"
        assert state.session_update["ssh_user"] == "root"
        assert state.session_update["winrm_user"] == "Administrator"
        assert state.session_update["winrm_port"] == 5986

    def test_local_submit_passes_session_id_into_process_env(self, tmp_path):
        import asyncio
        from types import SimpleNamespace

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)
        wf_file = tmp_path / "scan.yml"
        wf_file.write_text(
            "name: scan\njobs:\n  scan:\n    steps:\n      - run: echo ok\n"
        )
        captured_env: dict[str, str] = {}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "subprocess.Popen",
                lambda *args, **kwargs: captured_env.update(kwargs["env"]) or SimpleNamespace(pid=4321),
            )
            session = asyncio.run(
                mgr.submit(
                    str(wf_file),
                    target=SessionTarget.LOCAL,
                    env={"MODE": "fast"},
                )
            )

        assert session.remote_pid == 4321
        assert captured_env["SESSION_ID"] == session.id
        assert captured_env["MODE"] == "fast"

    @pytest.mark.asyncio
    async def test_prepare_cloud_submit_target_sequences_setup(self, tmp_path):
        from types import SimpleNamespace

        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(id="cloudprep", workflow_file="wf.yml")
        resolved = SimpleNamespace(os="windows", provider="static")
        instance = SimpleNamespace(ip="10.0.0.5")
        calls: list[tuple] = []

        with pytest.MonkeyPatch.context() as mp:
            class _Manager:
                def resolve(self, cfg):
                    assert cfg.profile == "demo-profile"
                    return resolved

            mp.setattr(
                "ofx.cloud.config.get_cloud_profile_manager",
                lambda: _Manager(),
            )

            def _save_session(current, update):
                calls.append(("save", update))
                return current.model_copy(update=update)

            async def _provision(current, resolved_cfg):
                calls.append(("provision", resolved_cfg))
                return current, instance

            async def _await_login(ip, resolved_cfg, *, is_windows):
                calls.append(("login", ip, resolved_cfg, is_windows))

            mp.setattr(mgr, "_save_session", _save_session)
            mp.setattr(mgr, "_provision_submit_cloud_instance", _provision)
            mp.setattr(mgr, "_await_submit_cloud_login", _await_login)

            prepared = await mgr._prepare_cloud_submit_target(session, "demo-profile")

        assert prepared.session.id == "cloudprep"
        assert prepared.resolved is resolved
        assert prepared.instance is instance
        assert prepared.os_type == "windows"
        assert prepared.is_windows is True
        assert calls[0][0] == "save"
        assert calls[1] == ("provision", resolved)
        assert calls[2] == ("login", "10.0.0.5", resolved, True)

    def test_prepare_cloud_submit_runtime_sets_at_rest_state(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(
            id="cloudrun",
            workflow_file="wf.yml",
            job_id="job-1",
            inputs={"targets_file": "/tmp/hosts.txt", "count": 5},
        )
        steps = [Step(run="echo ok")]

        prepared = mgr._prepare_cloud_submit_runtime(
            steps,
            session=session,
            env={"MODE": "fast"},
            workflow_name="wf-name",
            os_type="linux",
            is_windows=False,
        )

        assert prepared.session.at_rest_encrypted is True
        assert prepared.session.at_rest_key == prepared.at_rest_key
        assert prepared.remote_work_dir == "/tmp/.ses-cloudrun"
        assert prepared.remote_log == "/tmp/.ses-cloudrun/output.log"
        assert prepared.sep == "/"
        assert prepared.merged_env["targets_file"] == "/tmp/hosts.txt"
        assert prepared.merged_env["INPUT_TARGETS_FILE"] == "/tmp/hosts.txt"
        assert prepared.merged_env["count"] == "5"
        assert prepared.merged_env["INPUT_COUNT"] == "5"
        assert prepared.merged_env["MODE"] == "fast"
        assert "wf-name" in prepared.script_content

    def test_start_cloud_remote_submit_merges_uploaded_input_overrides_once(self, tmp_path):
        from types import SimpleNamespace

        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(
            id="cloudscript",
            workflow_file="wf.yml",
            inputs={"targets_file": str(tmp_path / "local-targets.txt")},
        )
        Path(session.inputs["targets_file"]).write_text("10.0.0.1\n")
        steps = [Step(run="echo ok")]
        uploads: list[tuple[str, str]] = []
        temp_uploads: list[tuple[str, str]] = []
        target = SimpleNamespace(
            resolved="resolved-config",
            instance=SimpleNamespace(ip="10.0.0.8"),
            os_type="linux",
            is_windows=False,
        )
        runtime = SimpleNamespace(
            session=session,
            remote_work_dir="/remote",
            at_rest_key="key123",
            remote_log="/remote/output.log",
            sep="/",
            merged_env={"MODE": "fast"},
        )
        remote = SimpleNamespace(
            upload=lambda local_path, remote_path: uploads.append((local_path, remote_path)),
            run=MagicMock(side_effect=["", "", "", "no\n", "42\n"]),
            cleanup=lambda: None,
        )

        with (
            patch.object(
                mgr,
                "_build_session_script_content",
                return_value="echo ok",
            ) as mock_build,
            patch.object(mgr, "_upload_script_files"),
            patch("ofx.cloud.runtime.create_remote_runner", return_value=remote),
            patch(
                "ofx.cloud.sessions.manager.upload_temp_content",
                side_effect=lambda _remote, content, remote_path, suffix="": temp_uploads.append((content, remote_path)),
            ),
        ):
            result = mgr._start_cloud_remote_submit(
                steps,
                target=target,
                runtime=runtime,
                workflow_dir=None,
                workflow_name="wf-name",
            )

        assert result.remote_pid == 42
        assert uploads == [(str(tmp_path / "local-targets.txt"), "/remote/local-targets.txt")]
        assert temp_uploads == [
            ("key123", "/remote/.skey"),
            ("echo ok", "/remote/run.sh"),
        ]
        assert remote.run.mock_calls == [
            (("mkdir -p /remote && chmod 700 /remote",), {}),
            (("chmod 600 /remote/.skey",), {}),
            (("chmod 700 /remote/run.sh",), {}),
            (("command -v tmux >/dev/null 2>&1 && echo yes || echo no",), {}),
            (("nohup bash /remote/run.sh > /remote/output.log 2>&1 & echo $!",), {}),
        ]
        mock_build.assert_called_once()
        _, kwargs = mock_build.call_args
        assert kwargs["session"].status == SessionStatus.UPLOADING
        assert kwargs["work_dir"] == "/remote"
        assert kwargs["workflow_name"] == "wf-name"
        assert kwargs["env"] == {
            "MODE": "fast",
            "targets_file": "/remote/local-targets.txt",
            "INPUT_TARGETS_FILE": "/remote/local-targets.txt",
        }
        assert kwargs["os_type"] == "linux"
        assert result.remote_launcher == "nohup"
        assert result.remote_tmux_session == ""

    def test_start_cloud_remote_submit_tmux_launcher_quotes_remote_paths(self, tmp_path):
        from types import SimpleNamespace

        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(id="cloudtmux", workflow_file="wf.yml")
        steps = [Step(run="echo ok")]
        target = SimpleNamespace(
            resolved="resolved-config",
            instance=SimpleNamespace(ip="10.0.0.8"),
            os_type="linux",
            is_windows=False,
        )
        runtime = SimpleNamespace(
            session=session,
            remote_work_dir="/remote dir",
            at_rest_key="key123",
            remote_log="/remote dir/output.log",
            sep="/",
            merged_env={"MODE": "fast"},
        )
        remote = SimpleNamespace(
            upload=lambda local_path, remote_path: None,
            run=MagicMock(side_effect=["", "", "", "yes\n", "", "9876\n"]),
            cleanup=lambda: None,
        )
        temp_uploads: list[tuple[str, str]] = []

        with (
            patch.object(mgr, "_build_session_script_content", return_value="echo ok"),
            patch.object(mgr, "_upload_script_files"),
            patch("ofx.cloud.runtime.create_remote_runner", return_value=remote),
            patch(
                "ofx.cloud.sessions.manager.upload_temp_content",
                side_effect=lambda _remote, content, remote_path, suffix="": temp_uploads.append((content, remote_path)),
            ),
        ):
            result = mgr._start_cloud_remote_submit(
                steps,
                target=target,
                runtime=runtime,
                workflow_dir=None,
                workflow_name="wf-name",
            )

        assert result.remote_pid == 9876
        assert result.remote_launcher == "tmux"
        assert result.remote_tmux_session == "ofx-ses-cloudtmux"
        tmux_start_cmd = remote.run.mock_calls[4].args[0]
        assert "tmux new-session -d -s ofx-ses-cloudtmux" in tmux_start_cmd
        assert "'/remote dir/run.sh'" in tmux_start_cmd
        assert "'/remote dir/output.log'" in tmux_start_cmd
        assert remote.run.mock_calls[5] == (("tmux list-panes -t ofx-ses-cloudtmux -F '#{pane_pid}' 2>/dev/null | head -n1",), {})

    def test_start_cloud_remote_submit_windows_uses_start_process_launcher(self, tmp_path):
        from types import SimpleNamespace

        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(id="cloudwin", workflow_file="wf.yml")
        steps = [Step(run="echo ok")]
        target = SimpleNamespace(
            resolved="resolved-config",
            instance=SimpleNamespace(ip="10.0.0.8"),
            os_type="windows",
            is_windows=True,
        )
        runtime = SimpleNamespace(
            session=session,
            remote_work_dir=r"C:\Windows\Temp\.ses-cloudwin",
            at_rest_key="key123",
            remote_log=r"C:\Windows\Temp\.ses-cloudwin\output.log",
            sep="\\",
            merged_env={"MODE": "fast"},
        )
        remote = SimpleNamespace(
            upload=lambda local_path, remote_path: None,
            run=MagicMock(side_effect=["", "", "4321\n"]),
            cleanup=lambda: None,
        )
        temp_uploads: list[tuple[str, str]] = []

        with (
            patch.object(mgr, "_build_session_script_content", return_value="echo ok"),
            patch.object(mgr, "_upload_script_files"),
            patch("ofx.cloud.runtime.create_remote_runner", return_value=remote),
            patch(
                "ofx.cloud.sessions.manager.upload_temp_content",
                side_effect=lambda _remote, content, remote_path, suffix="": temp_uploads.append((content, remote_path)),
            ),
        ):
            result = mgr._start_cloud_remote_submit(
                steps,
                target=target,
                runtime=runtime,
                workflow_dir=None,
                workflow_name="wf-name",
            )

        assert result.remote_pid == 4321
        assert result.remote_launcher == "start-process"
        assert result.remote_tmux_session == ""

    @pytest.mark.asyncio
    async def test_submit_cloud_uses_prepared_target_and_runtime_objects(self, tmp_path):
        from types import SimpleNamespace

        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(id="cloudsubmit", workflow_file="wf.yml")
        steps = [Step(run="echo ok")]
        target = SimpleNamespace(
            session=session,
            resolved="resolved-config",
            instance=SimpleNamespace(ip="10.0.0.8"),
            os_type="linux",
            is_windows=False,
        )
        runtime = SimpleNamespace(
            session=session.model_copy(update={"at_rest_encrypted": True}),
            remote_work_dir="/tmp/.ses-cloudsubmit",
            at_rest_key="key123",
            remote_log="/tmp/.ses-cloudsubmit/output.log",
            sep="/",
            merged_env={"MODE": "fast"},
            script_content="echo ok",
        )
        calls: list[tuple[str, object]] = []

        with pytest.MonkeyPatch.context() as mp:
            async def _prepare_target(current, profile):
                calls.append(("target", profile))
                return target

            def _prepare_runtime(steps_arg, **kwargs):
                calls.append(("runtime", kwargs))
                return runtime

            def _start_remote(steps_arg, **kwargs):
                calls.append(("start", kwargs))
                return runtime.session.model_copy(update={"remote_pid": 42})

            mp.setattr(mgr, "_prepare_cloud_submit_target", _prepare_target)
            mp.setattr(mgr, "_prepare_cloud_submit_runtime", _prepare_runtime)
            mp.setattr(mgr, "_start_cloud_remote_submit", _start_remote)

            result = await mgr._submit_cloud(
                session,
                steps,
                {"MODE": "fast"},
                "demo-profile",
                workflow_dir=None,
                workflow_name="wf-name",
            )

        assert result.remote_pid == 42
        assert calls[0] == ("target", "demo-profile")
        assert calls[1][0] == "runtime"
        assert calls[1][1]["session"] == target.session
        assert calls[1][1]["os_type"] == "linux"
        assert calls[2][0] == "start"
        assert calls[2][1]["target"] is target
        assert calls[2][1]["runtime"] is runtime

class TestCloudCancelTmux:
    @pytest.mark.asyncio
    async def test_cancel_cloud_tmux_uses_kill_session(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        session = Session(
            id="tmuxkill",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.RUNNING,
            instance_ip="10.0.0.10",
            remote_pid=1234,
            remote_log_file="/tmp/output.log",
            os_type="linux",
            remote_launcher="tmux",
            remote_tmux_session="ofx-ses-tmuxkill",
        )
        store.save(session)
        mgr = SessionManager(store=store)

        seen: list[str] = []

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                seen.append(cmd)
                return ""

            def cleanup(self):
                return None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            out = await mgr.cancel("tmuxkill")

        assert out.status == SessionStatus.CANCELED
        assert any("tmux kill-session -t ofx-ses-tmuxkill" in c for c in seen)

class TestCloudAutoDestroyAfterFetch:
    @pytest.mark.asyncio
    async def test_auto_destroy_after_fetch_non_static_enabled(self, tmp_path):
        from ofx.cloud.sessions import SessionManager
        from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
        from ofx.cloud.sessions.store import SessionStore
        from ofx.models.cloud import CloudConfig

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(
            id="autod1",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.COMPLETED,
            cloud_provider="digitalocean",
            instance_id="i-123",
            instance_ip="10.0.0.5",
            auto_destroy=True,
        )

        destroyed: list[str] = []

        class _FakeProvider:
            async def destroy_instance(self, instance_id):
                destroyed.append(instance_id)

        class _FakeProfileMgr:
            def resolve(self, cfg):
                return CloudConfig(provider="digitalocean")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "ofx.cloud.config.get_cloud_profile_manager",
                lambda: _FakeProfileMgr(),
            )
            mp.setattr(
                "ofx.cloud.CloudProviderRegistry.create",
                lambda provider, **kwargs: _FakeProvider(),
            )
            out = await mgr._auto_destroy_after_fetch(session)

        assert destroyed == ["i-123"]
        assert out.instance_id == ""
        assert out.instance_ip == ""

    @pytest.mark.asyncio
    async def test_auto_destroy_after_fetch_skips_static(self, tmp_path):
        from ofx.cloud.sessions import SessionManager
        from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
        from ofx.cloud.sessions.store import SessionStore

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(
            id="autod2",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.COMPLETED,
            cloud_provider="static",
            instance_id="i-static",
            instance_ip="10.0.0.6",
            auto_destroy=True,
        )

        out = await mgr._auto_destroy_after_fetch(session)
        assert out.instance_id == "i-static"
        assert out.instance_ip == "10.0.0.6"

    @pytest.mark.asyncio
    async def test_auto_destroy_after_fetch_skips_when_disabled(self, tmp_path):
        from ofx.cloud.sessions import SessionManager
        from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
        from ofx.cloud.sessions.store import SessionStore

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(
            id="autod3",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.COMPLETED,
            cloud_provider="digitalocean",
            instance_id="i-keep",
            instance_ip="10.0.0.7",
            auto_destroy=False,
        )

        out = await mgr._auto_destroy_after_fetch(session)
        assert out.instance_id == "i-keep"
        assert out.instance_ip == "10.0.0.7"

class TestCloudDestroy:
    @pytest.mark.asyncio
    async def test_destroy_cloud_non_static_marks_destroyed(self, tmp_path):
        from ofx.cloud.sessions import SessionManager
        from ofx.models.cloud import CloudConfig

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(
            id="destroy1",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.COMPLETED,
            cloud_provider="digitalocean",
            instance_id="i-123",
            instance_ip="10.0.0.5",
        )
        store.save(session)

        destroyed: list[str] = []

        class _FakeProvider:
            async def destroy_instance(self, instance_id):
                destroyed.append(instance_id)

        class _FakeProfileMgr:
            def resolve(self, cfg):
                return CloudConfig(provider="digitalocean")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "ofx.cloud.config.get_cloud_profile_manager",
                lambda: _FakeProfileMgr(),
            )
            mp.setattr(
                "ofx.cloud.CloudProviderRegistry.create",
                lambda provider, **kwargs: _FakeProvider(),
            )
            out = await mgr.destroy("destroy1")

        assert destroyed == ["i-123"]
        assert out.status == SessionStatus.DESTROYED
        assert out.instance_id == "i-123"
        assert out.instance_ip == "10.0.0.5"

class TestCloudFetchMaterialization:
    @pytest.mark.asyncio
    async def test_fetch_cloud_uses_encrypted_archive_when_available(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(
            id="fetchenc",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.COMPLETED,
            instance_ip="10.0.0.8",
            remote_work_dir="/tmp/.ses-fetchenc",
            remote_log_file="/tmp/.ses-fetchenc/output.log",
            os_type="linux",
            at_rest_encrypted=True,
            at_rest_key="secret-key",
        )
        results = tmp_path / "results"

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                raise AssertionError(
                    "remote.run should not be used when archive download succeeds"
                )

            def download(self, remote_path, local_path):
                path = Path(local_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                if remote_path.endswith("output.enc"):
                    path.write_text("encrypted-bytes")
                    return
                if remote_path.endswith("output.log"):
                    path.write_text("log output")
                    return
                raise AssertionError(f"unexpected download path: {remote_path}")

            def cleanup(self):
                return None

        decrypted: list[tuple[Path, str, Path]] = []

        def _fake_decrypt(enc_file: Path, at_rest_key: str, output_dir: Path) -> None:
            decrypted.append((enc_file, at_rest_key, output_dir))
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "result.txt").write_text("ok")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            mp.setattr(
                "ofx.cloud.sessions.manager._decrypt_at_rest_openssl",
                _fake_decrypt,
            )
            await mgr._fetch_cloud_results(session, results)

        assert decrypted == [
            (results.parent / "output_fetchenc.enc", "secret-key", results)
        ]
        assert (results / "result.txt").read_text() == "ok"
        assert (results / "output.log").read_text() == "log output"
        assert not (results.parent / "output_fetchenc.enc").exists()

    @pytest.mark.asyncio
    async def test_fetch_cloud_falls_back_to_individual_outputs(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = SessionManager(store=store)
        session = Session(
            id="fetchplain",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.COMPLETED,
            instance_ip="10.0.0.9",
            remote_work_dir="/tmp/work dir",
            remote_log_file="/tmp/work dir/output.log",
            os_type="linux",
            at_rest_encrypted=True,
            at_rest_key="secret-key",
        )
        results = tmp_path / "results"
        seen_commands: list[str] = []

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                seen_commands.append(cmd)
                return "one.txt\ntwo.txt\n"

            def download(self, remote_path, local_path):
                if remote_path.endswith("output.enc"):
                    raise FileNotFoundError("missing archive")
                Path(local_path).write_text(Path(remote_path).name)

            def cleanup(self):
                return None

        def _unexpected_decrypt(*args, **kwargs):
            raise AssertionError("decrypt should not run when archive download fails")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            mp.setattr(
                "ofx.cloud.sessions.manager._decrypt_at_rest_openssl",
                _unexpected_decrypt,
            )
            await mgr._fetch_cloud_results(session, results)

        assert seen_commands == ["ls -1 '/tmp/work dir/output' 2>/dev/null"]
        assert (results / "one.txt").read_text() == "one.txt"
        assert (results / "two.txt").read_text() == "two.txt"
        assert (results / "output.log").read_text() == "output.log"

class TestCloudLogs:
    @pytest.mark.asyncio
    async def test_logs_cloud_returns_remote_tail_output(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        session = Session(
            id="cloudlogs1",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.RUNNING,
            instance_ip="10.0.0.7",
            remote_log_file="/tmp/.ses-cloudlogs1/output.log",
            os_type="linux",
        )
        store.save(session)
        mgr = SessionManager(store=store)

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                return "log line\n"

            def cleanup(self):
                return None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            output = await mgr.logs(session.id, tail=10)

        assert output == "log line\n"

    @pytest.mark.asyncio
    async def test_logs_cloud_returns_error_text_on_reconnect_failure(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        session = Session(
            id="cloudlogs2",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.RUNNING,
            instance_ip="10.0.0.8",
            remote_log_file="/tmp/.ses-cloudlogs2/output.log",
            os_type="linux",
        )
        store.save(session)
        mgr = SessionManager(store=store)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                mgr,
                "_reconnect",
                lambda s: (_ for _ in ()).throw(ConnectionRefusedError("refused")),
            )
            output = await mgr.logs(session.id, tail=10)

        assert "cannot retrieve logs" in output
        assert "refused" in output

    @pytest.mark.asyncio
    async def test_logs_local_returns_fallback_when_file_cannot_be_read(self, tmp_path):
        from ofx.cloud.sessions import SessionManager

        store = SessionStore(base_dir=tmp_path / "sessions")
        log_path = tmp_path / "output.log"
        log_path.write_text("line1\nline2\n")
        session = Session(
            id="locallogs1",
            workflow_file="wf.yml",
            target=SessionTarget.LOCAL,
            status=SessionStatus.RUNNING,
            remote_log_file=str(log_path),
            os_type="linux",
        )
        store.save(session)
        mgr = SessionManager(store=store)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(Path, "read_text", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")))
            output = await mgr.logs(session.id, tail=10)

        assert output == "(cannot read log)"

def _make_manager(store: SessionStore, search_dir: Path):
    """Create a SessionManager with patched workflow search dirs.

    Uses a snapshot of the *original* DEFAULT_WORKFLOWS_DIRS to avoid
    accumulating paths across test runs (test pollution).
    """
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager(store=store)
    import ofx.settings as settings_mod

    settings_mod.DEFAULT_WORKFLOWS_DIRS = [search_dir, *_ORIGINAL_WORKFLOW_DIRS]
    return mgr

_ORIGINAL_WORKFLOW_DIRS: list[Path] = list(_settings_mod.DEFAULT_WORKFLOWS_DIRS)

class TestSessionWinRMFields:
    """Tests that Session model stores and rounds-trips WinRM connection fields."""

    def test_session_defaults_to_linux_ssh(self):
        from ofx.cloud.sessions.models import Session

        s = Session(id="abc12345", workflow_file="wf.yml")
        assert s.os_type == "linux"
        assert s.winrm_port == 5985
        assert s.winrm_ssl is False
        assert s.winrm_transport == "ntlm"
        assert s.winrm_user == "Administrator"

    def test_session_stores_winrm_fields(self):
        from ofx.cloud.sessions.models import Session

        s = Session(
            id="abc12345",
            workflow_file="wf.yml",
            os_type="windows",
            winrm_port=5986,
            winrm_ssl=True,
            winrm_transport="credssp",
            winrm_user="admin",
            ssh_password="secret",
        )
        assert s.winrm_port == 5986
        assert s.winrm_ssl is True
        assert s.winrm_transport == "credssp"
        assert s.winrm_user == "admin"

    def test_session_roundtrips_through_json(self, tmp_path):
        """WinRM fields survive a JSON serialize/deserialize cycle."""
        from ofx.cloud.sessions.models import Session

        s = Session(
            id="abc12345",
            workflow_file="wf.yml",
            os_type="windows",
            winrm_port=5986,
            winrm_ssl=True,
            winrm_user="svcacct",
        )
        data = json.loads(s.model_dump_json())
        s2 = Session.model_validate(data)
        assert s2.winrm_port == 5986
        assert s2.winrm_ssl is True
        assert s2.winrm_user == "svcacct"

class TestCheckCloudStatusNoPid:
    """Tests for _check_cloud_status when remote_pid is None."""

    def _make_mgr(self, tmp_path):
        from ofx.cloud.sessions import SessionManager
        from ofx.cloud.sessions.store import SessionStore

        store = SessionStore(base_dir=tmp_path)
        mgr = SessionManager.__new__(SessionManager)
        mgr.store = store
        mgr._poll_failures = {}
        return mgr

    def _make_running_session(self, pid=None):
        from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget

        return Session(
            id="abc12345",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.RUNNING,
            instance_ip="10.0.0.1",
            remote_pid=pid,
            remote_log_file="/tmp/output.log",
            os_type="linux",
        )

    @pytest.mark.asyncio
    async def test_no_pid_reads_log_marker_done(self, tmp_path):
        """When remote_pid is None, status is inferred from log marker alone."""
        from ofx.cloud.sessions.models import SessionStatus

        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session(pid=None)

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                return "__TASK_OK__"

            def cleanup(self):
                pass

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            result = await mgr._check_cloud_status(session)

        assert result.status == SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_no_pid_reads_log_marker_fail(self, tmp_path):
        """When remote_pid is None and log shows __TASK_ERR__, session is failed."""
        from ofx.cloud.sessions.models import SessionStatus

        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session(pid=None)

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                return "__TASK_ERR__"

            def cleanup(self):
                pass

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            result = await mgr._check_cloud_status(session)

        assert result.status == SessionStatus.FAILED

    @pytest.mark.asyncio
    async def test_no_pid_reconnect_failure_keeps_running(self, tmp_path):
        """If reconnect fails with no PID, session stays RUNNING (unknown)."""
        from ofx.cloud.sessions.models import SessionStatus

        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session(pid=None)

        def _failing_reconnect(s):
            raise ConnectionRefusedError("refused")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", _failing_reconnect)
            result = await mgr._check_cloud_status(session)

        assert result.status == SessionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_no_pid_tmux_alive_keeps_running(self, tmp_path):
        """When no PID but tmux launcher is alive, keep RUNNING."""
        from ofx.cloud.sessions.models import SessionStatus

        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session(pid=None).model_copy(
            update={
                "remote_launcher": "tmux",
                "remote_tmux_session": "ofx-ses-abc12345",
            }
        )

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                if "tail" in cmd:
                    return ""
                if "tmux has-session" in cmd:
                    return "alive"
                return ""

            def cleanup(self):
                pass

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            result = await mgr._check_cloud_status(session)

        assert result.status == SessionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_no_pid_status_quotes_remote_log_path_with_spaces(self, tmp_path):
        """No-PID status probes shell-quote remote log paths."""
        from ofx.cloud.sessions.models import SessionStatus

        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session(pid=None).model_copy(
            update={"remote_log_file": "/tmp/work dir/output.log"}
        )
        seen: list[str] = []

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                seen.append(cmd)
                return "__TASK_OK__"

            def cleanup(self):
                pass

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            result = await mgr._check_cloud_status(session)

        assert result.status == SessionStatus.COMPLETED
        assert seen == ["tail -5 '/tmp/work dir/output.log' 2>/dev/null"]

class TestCloudStatusBackoff:
    """Tests for exponential backoff and circuit breaker in _check_cloud_status."""

    def _make_mgr(self, tmp_path):
        from ofx.cloud.sessions import SessionManager
        from ofx.cloud.sessions.store import SessionStore

        store = SessionStore(base_dir=tmp_path)
        mgr = SessionManager.__new__(SessionManager)
        mgr.store = store
        mgr._poll_failures = {}
        return mgr

    def _make_running_session(self, pid=42):
        return Session(
            id="back0ff1",
            workflow_file="wf.yml",
            target=SessionTarget.CLOUD,
            status=SessionStatus.RUNNING,
            instance_ip="10.0.0.1",
            remote_pid=pid,
            remote_log_file="/tmp/output.log",
            os_type="linux",
        )

    @pytest.mark.asyncio
    async def test_reconnect_failure_increments_counter(self, tmp_path):
        """Each reconnect failure bumps _poll_failures for that session."""
        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session()

        def _fail(s):
            raise ConnectionRefusedError("refused")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", _fail)
            await mgr._check_cloud_status(session)

        assert mgr._poll_failures["back0ff1"] == 1

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", _fail)
            await mgr._check_cloud_status(session)

        assert mgr._poll_failures["back0ff1"] == 2

    @pytest.mark.asyncio
    async def test_tmux_pid_status_quotes_tmux_session_name(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session().model_copy(
            update={
                "remote_launcher": "tmux",
                "remote_tmux_session": "tmux name",
            }
        )
        seen: list[str] = []

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                seen.append(cmd)
                if "tmux has-session" in cmd:
                    return "alive"
                return ""

            def cleanup(self):
                pass

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            await mgr._check_cloud_status(session)

        assert seen[0] == "tmux has-session -t 'tmux name' 2>/dev/null && echo alive || echo dead"

    @pytest.mark.asyncio
    async def test_success_resets_failure_counter(self, tmp_path):
        """A successful probe resets the failure counter to zero."""
        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session()
        mgr._poll_failures["back0ff1"] = 5

        class _FakeRemote:
            def run(self, cmd, timeout=None):
                if "kill -0" in cmd:
                    return "alive"
                return ""

            def cleanup(self):
                pass

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", lambda s: _FakeRemote())
            await mgr._check_cloud_status(session)

        assert mgr._poll_failures["back0ff1"] == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_marks_unreachable(self, tmp_path):
        """After _MAX_CONSECUTIVE_FAILURES, session becomes UNREACHABLE."""
        from ofx.cloud.sessions import manager as mgr_mod

        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session()
        mgr._poll_failures["back0ff1"] = mgr_mod._MAX_CONSECUTIVE_FAILURES - 1

        def _fail(s):
            raise ConnectionRefusedError("refused")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", _fail)
            result = await mgr._check_cloud_status(session)

        assert result.status == SessionStatus.UNREACHABLE
        assert "Unreachable" in result.error

    @pytest.mark.asyncio
    async def test_circuit_breaker_no_pid_marks_unreachable(self, tmp_path):
        """Circuit breaker works in the no-PID path too."""
        from ofx.cloud.sessions import manager as mgr_mod

        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session(pid=None)
        mgr._poll_failures["back0ff1"] = mgr_mod._MAX_CONSECUTIVE_FAILURES - 1

        def _fail(s):
            raise ConnectionRefusedError("refused")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", _fail)
            result = await mgr._check_cloud_status(session)

        assert result.status == SessionStatus.UNREACHABLE

    @pytest.mark.asyncio
    async def test_below_threshold_stays_running(self, tmp_path):
        """Failures below the threshold keep session as RUNNING."""
        mgr = self._make_mgr(tmp_path)
        session = self._make_running_session()

        def _fail(s):
            raise ConnectionRefusedError("refused")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mgr, "_reconnect", _fail)
            result = await mgr._check_cloud_status(session)

        assert result.status == SessionStatus.RUNNING
        assert mgr._poll_failures["back0ff1"] == 1
    def test_session_model_tmux_fields_roundtrip(self):
        s = Session(
            id="tmux1234",
            workflow_file="wf.yml",
            remote_tmux_session="ofx-ses-tmux1234",
            remote_launcher="tmux",
        )
        dumped = s.model_dump()
        restored = Session.model_validate(dumped)
        assert restored.remote_tmux_session == "ofx-ses-tmux1234"
        assert restored.remote_launcher == "tmux"

class TestSessionManagerScriptBundling:
    def _make_step(self, **kwargs) -> Step:
        return Step.model_validate(kwargs)

    def test_stage_script_files_writes_bundle_for_inline_script(self, tmp_path):
        from ofx.cloud.sessions.manager import SessionManager

        mgr = SessionManager(store=SessionStore(base_dir=tmp_path / "sessions"))
        work_dir = tmp_path / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        steps = [self._make_step(name="s0", script='print("BUNDLE_INLINE_OK")')]

        mgr._stage_script_files(steps, work_dir)

        bundled = work_dir / ".ofx_step_0.py"
        assert bundled.exists()
        bundled_text = bundled.read_text()
        assert "BUNDLE_INLINE_OK" not in bundled_text
        assert "_m.loads" in bundled_text or "base64.b64decode" in bundled_text

    def test_stage_script_files_writes_bundle_for_script_file(self, tmp_path):
        from ofx.cloud.sessions.manager import SessionManager

        src = tmp_path / "in.py"
        src.write_text('print("BUNDLE_FILE_OK")\n')
        mgr = SessionManager(store=SessionStore(base_dir=tmp_path / "sessions"))
        work_dir = tmp_path / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        steps = [self._make_step(name="s0", script_file=str(src))]

        mgr._stage_script_files(steps, work_dir)

        bundled = work_dir / ".ofx_step_0.py"
        assert bundled.exists()
        bundled_text = bundled.read_text()
        assert "BUNDLE_FILE_OK" not in bundled_text
        assert "_m.loads" in bundled_text or "base64.b64decode" in bundled_text

    def test_stage_script_files_resolves_relative_script_file_from_workflow_dir(
        self,
        tmp_path,
    ):
        from ofx.cloud.sessions.manager import SessionManager

        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()
        src = workflow_dir / "relative.py"
        src.write_text('print("RELATIVE_BUNDLE_OK")\n')
        mgr = SessionManager(store=SessionStore(base_dir=tmp_path / "sessions"))
        work_dir = tmp_path / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        steps = [self._make_step(name="s0", script_file="relative")]

        mgr._stage_script_files(steps, work_dir, workflow_dir=workflow_dir)

        bundled = work_dir / ".ofx_step_0.py"
        assert bundled.exists()
        bundled_text = bundled.read_text()
        assert "RELATIVE_BUNDLE_OK" not in bundled_text
        assert "_m.loads" in bundled_text or "base64.b64decode" in bundled_text

    def test_upload_script_files_uploads_only_python_steps(self, tmp_path):
        from ofx.cloud.sessions.manager import SessionManager

        uploads: list[tuple[str, str, str]] = []

        class _Remote:
            def upload(self, local_path, remote_path):
                uploads.append((local_path, remote_path, Path(local_path).read_text()))

        src = tmp_path / "in.py"
        src.write_text('print("BUNDLE_UPLOAD_OK")\n')
        mgr = SessionManager(store=SessionStore(base_dir=tmp_path / "sessions"))
        steps = [
            self._make_step(name="inline", script='print("INLINE_OK")'),
            self._make_step(name="cmd", run="echo hi"),
            self._make_step(name="file", script_file=str(src)),
        ]

        mgr._upload_script_files(steps, _Remote(), "/tmp/ofx-run", is_windows=False)

        assert [item[1] for item in uploads] == [
            "/tmp/ofx-run/.ofx_step_0.py",
            "/tmp/ofx-run/.ofx_step_2.py",
        ]
        assert all("INLINE_OK" not in content for _, _, content in uploads)
        assert all("BUNDLE_UPLOAD_OK" not in content for _, _, content in uploads)

    def test_upload_script_files_resolves_relative_script_file_from_workflow_dir(
        self,
        tmp_path,
    ):
        from ofx.cloud.sessions.manager import SessionManager

        uploads: list[tuple[str, str, str]] = []

        class _Remote:
            def upload(self, local_path, remote_path):
                uploads.append((local_path, remote_path, Path(local_path).read_text()))

        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()
        src = workflow_dir / "relative.py"
        src.write_text('print("RELATIVE_UPLOAD_OK")\n')
        mgr = SessionManager(store=SessionStore(base_dir=tmp_path / "sessions"))
        steps = [self._make_step(name="s0", script_file="relative")]

        mgr._upload_script_files(
            steps,
            _Remote(),
            "/tmp/ofx-run",
            is_windows=False,
            workflow_dir=workflow_dir,
        )

        assert [item[1] for item in uploads] == ["/tmp/ofx-run/.ofx_step_0.py"]
        assert "RELATIVE_UPLOAD_OK" not in uploads[0][2]
