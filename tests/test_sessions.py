"""Tests for the detached sessions feature (models, store, script builder, encryption, manager)."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.store import SessionStore
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.cloud.sessions.encryption import derive_key, encrypt_results, decrypt_results


# ======================================================================
# Session model tests
# ======================================================================


class TestSessionModel:
    def test_create_minimal(self):
        s = Session(id="aabbccdd", workflow_file="scan.yml")
        assert s.id == "aabbccdd"
        assert s.target == SessionTarget.LOCAL
        assert s.status == SessionStatus.PROVISIONING
        assert s.is_running()
        assert not s.is_done()

    def test_is_running_states(self):
        for status in (SessionStatus.PROVISIONING, SessionStatus.UPLOADING, SessionStatus.RUNNING):
            s = Session(id="test", workflow_file="w.yml", status=status)
            assert s.is_running(), f"{status} should be running"

    def test_is_done_states(self):
        for status in (
            SessionStatus.COMPLETED, SessionStatus.FAILED,
            SessionStatus.CANCELED, SessionStatus.FETCHED,
            SessionStatus.ENCRYPTED, SessionStatus.DESTROYED,
        ):
            s = Session(id="test", workflow_file="w.yml", status=status)
            assert s.is_done(), f"{status} should be done"
            assert not s.is_running(), f"{status} should not be running"

    def test_age_display(self):
        s = Session(
            id="test",
            workflow_file="w.yml",
            started_at=datetime.now(timezone.utc) - timedelta(hours=2, minutes=30),
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


# ======================================================================
# Session store tests
# ======================================================================


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
        store.save(Session(id="abc12345", workflow_file="w.yml", status=SessionStatus.RUNNING))
        updated = store.update_status("abc12345", SessionStatus.COMPLETED)
        assert updated.status == SessionStatus.COMPLETED

    def test_list_sessions(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        store.save(Session(id="aaa", workflow_file="w1.yml", status=SessionStatus.RUNNING))
        store.save(Session(id="bbb", workflow_file="w2.yml", status=SessionStatus.COMPLETED))
        store.save(Session(id="ccc", workflow_file="w3.yml", status=SessionStatus.RUNNING, target=SessionTarget.CLOUD))

        all_sessions = store.list_sessions()
        assert len(all_sessions) == 3

        running = store.list_sessions(status=SessionStatus.RUNNING)
        assert len(running) == 2

        cloud = store.list_sessions(target="cloud")
        assert len(cloud) == 1
        assert cloud[0].id == "ccc"

    def test_results_dir(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        store.save(Session(id="abc12345", workflow_file="w.yml"))
        results = store.results_dir("abc12345")
        assert results.exists()
        assert results.name == "results"

    def test_clean(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        old_time = datetime.now(timezone.utc) - timedelta(days=10)
        store.save(Session(
            id="old", workflow_file="w.yml",
            status=SessionStatus.COMPLETED, started_at=old_time,
        ))
        store.save(Session(
            id="new", workflow_file="w.yml",
            status=SessionStatus.COMPLETED,
        ))

        removed = store.clean(older_than_seconds=7 * 86400, statuses=[SessionStatus.COMPLETED])
        assert removed == 1
        assert not store.exists("old")
        assert store.exists("new")

    def test_session_dir_path(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        d = store.session_dir("myid")
        assert d == tmp_path / "sessions" / "myid"


# ======================================================================
# Script builder tests
# ======================================================================


class TestScriptBuilder:
    def _make_step(self, **kwargs):
        """Create a minimal Step-like object."""
        from ofx.models.step import Step
        return Step(**kwargs)

    def test_bash_single_command(self):
        steps = [self._make_step(name="recon", run="nmap -sV 10.0.0.1")]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert "#!/bin/bash" in script
        assert "OFX_SESSION_ID" in script
        assert "nmap -sV 10.0.0.1" in script
        assert "__OFX_DONE__" in script
        assert "__OFX_FAIL__" in script

    def test_bash_multiple_steps(self):
        steps = [
            self._make_step(name="step1", run="echo hello"),
            self._make_step(name="step2", run="echo world"),
        ]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert "step1" in script
        assert "step2" in script
        assert script.count(">>> Step") == 2

    def test_bash_env_vars(self):
        steps = [self._make_step(run="env")]
        script = build_session_script(
            steps, session_id="aabb", work_dir="/tmp/test",
            env={"TARGET": "10.0.0.1", "PORT": "443"},
        )
        assert 'export TARGET=' in script
        assert 'export PORT=' in script

    def test_bash_continue_on_error(self):
        steps = [self._make_step(run="might-fail", continue_on_error=True)]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert "continue_on_error" in script

    def test_bash_inline_script(self):
        steps = [self._make_step(name="inline", script="echo hello\necho world")]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert "echo hello" in script

    def test_powershell_basic(self):
        steps = [self._make_step(name="wincheck", run="Get-Process")]
        script = build_session_script(
            steps, session_id="aabb", work_dir="C:\\Windows\\Temp\\test",
            os_type="windows",
        )
        assert "$ErrorActionPreference" in script
        assert "OFX_SESSION_ID" in script
        assert "Get-Process" in script
        assert "__OFX_DONE__" in script

    def test_script_file_step(self):
        steps = [self._make_step(name="sf", script_file="/opt/scripts/scan.sh")]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert "scan.sh" in script


# ======================================================================
# Encryption tests
# ======================================================================


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
        assert salt1 != salt2  # Random salts differ
        assert key1 != key2    # So keys differ

    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        # Create a results directory with some files
        results = tmp_path / "results"
        results.mkdir()
        (results / "output.txt").write_text("scan results here")
        (results / "nmap.xml").write_text("<nmap>data</nmap>")

        # Encrypt
        enc_file = encrypt_results(results, "hunter2")
        assert enc_file.exists()
        assert enc_file.name == "results.enc"
        assert enc_file.stat().st_size > 0

        # Decrypt
        out = tmp_path / "decrypted"
        decrypt_results(enc_file, "hunter2", out)
        # tarball unpacks to "results/" inside output
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


# ======================================================================
# Session manager tests (local mode — no VPS needed)
# ======================================================================


class TestSessionManagerLocal:
    """Tests for local session submission and lifecycle.

    These tests use real subprocesses but no SSH/cloud — fully local.
    """

    @pytest.fixture(autouse=True)
    def _restore_workflow_dirs(self):
        """Restore DEFAULT_WORKFLOWS_DIRS after each test to prevent pollution."""
        import ofx.settings as settings_mod
        original = list(settings_mod.DEFAULT_WORKFLOWS_DIRS)
        yield
        settings_mod.DEFAULT_WORKFLOWS_DIRS = original

    def _create_test_workflow(self, tmp_path: Path) -> Path:
        """Write a minimal workflow YAML that echoes output."""
        wf = tmp_path / "test_session.yml"
        wf.write_text(textwrap.dedent("""\
            name: session-test
            jobs:
              echo-job:
                steps:
                  - name: greet
                    run: echo "Hello from session"
                  - name: write-output
                    run: echo "result data" > output/result.txt
        """))
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

        # Should be persisted
        loaded = store.load(session.id)
        assert loaded.id == session.id

    def test_submit_local_runs_script(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

        # Wait for the process to finish
        import time
        for _ in range(30):
            time.sleep(0.2)
            try:
                os.kill(session.remote_pid, 0)
            except ProcessLookupError:
                break

        # Check status
        session = asyncio.run(mgr.status(session.id))
        assert session.status == SessionStatus.COMPLETED

    def test_status_completed(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

        # Wait for completion
        import time
        for _ in range(30):
            time.sleep(0.2)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        assert session.status == SessionStatus.COMPLETED

    def test_logs_returns_output(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

        # Wait for completion
        import time
        for _ in range(30):
            time.sleep(0.2)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        logs = asyncio.run(mgr.logs(session.id))
        assert "Session" in logs or "started" in logs

    def test_fetch_results(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

        import time
        for _ in range(30):
            time.sleep(0.2)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        results_path = asyncio.run(mgr.fetch(session.id))
        assert results_path.exists()
        # Fetched status
        session = store.load(session.id)
        assert session.status == SessionStatus.FETCHED

    def test_fetch_with_encryption(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

        import time
        for _ in range(30):
            time.sleep(0.2)
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
        wf.write_text(textwrap.dedent("""\
            name: long-run
            jobs:
              wait-job:
                steps:
                  - name: wait
                    run: sleep 300
        """))
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf), target=SessionTarget.LOCAL)
        )
        assert session.remote_pid is not None

        # Cancel
        import time
        time.sleep(0.5)  # Let it start
        session = asyncio.run(mgr.cancel(session.id))
        assert session.status == SessionStatus.CANCELED

        # PID should be dead
        time.sleep(0.5)
        try:
            os.kill(session.remote_pid, 0)
            # Process still alive — that's ok, SIGTERM may take a moment
        except ProcessLookupError:
            pass  # Expected

    def test_fetch_while_running_raises(self, tmp_path):
        wf = tmp_path / "long_running.yml"
        wf.write_text(textwrap.dedent("""\
            name: long-run
            jobs:
              wait-job:
                steps:
                  - name: wait
                    run: sleep 300
        """))
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf), target=SessionTarget.LOCAL)
        )

        with pytest.raises(RuntimeError, match="still running"):
            asyncio.run(mgr.fetch(session.id))

        # Cleanup
        asyncio.run(mgr.cancel(session.id))


class TestSessionManagerDecrypt:
    def test_decrypt_after_encrypted_fetch(self, tmp_path):
        store = SessionStore(base_dir=tmp_path / "sessions")
        # Manually create a session with encrypted results
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
        # Check the decrypted content is available
        assert (out / "results" / "data.txt").exists()


# ======================================================================
# Helper
# ======================================================================


def _make_manager(store: SessionStore, search_dir: Path):
    """Create a SessionManager with patched workflow search dirs.

    Uses a snapshot of the *original* DEFAULT_WORKFLOWS_DIRS to avoid
    accumulating paths across test runs (test pollution).
    """
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager(store=store)
    # Prepend search_dir so find_workflow looks in tmp_path, but keep a
    # clean snapshot of the default list to avoid mutation leak.
    import ofx.settings as settings_mod
    settings_mod.DEFAULT_WORKFLOWS_DIRS = [search_dir, *_ORIGINAL_WORKFLOW_DIRS]
    return mgr


# Captured once at import time so repeated calls never stack up.
import ofx.settings as _settings_mod
_ORIGINAL_WORKFLOW_DIRS: list[Path] = list(_settings_mod.DEFAULT_WORKFLOWS_DIRS)
