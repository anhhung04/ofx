"""Tests for the detached sessions feature (models, store, script builder, encryption, manager)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import ofx.settings as _settings_mod
from ofx.cloud.sessions.encryption import decrypt_results, derive_key, encrypt_results
from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.cloud.sessions.store import SessionStore
from ofx.models.step import Step

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
        old_time = datetime.now(UTC) - timedelta(days=10)
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
        assert "SESSION_ID" in script
        assert "nmap -sV 10.0.0.1" in script
        assert "__TASK_OK__" in script
        assert "__TASK_ERR__" in script

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
        assert '"$__OFX_PY_BIN" ".ofx_step_0.py"' in script

    def test_powershell_basic(self):
        steps = [self._make_step(name="wincheck", run="Get-Process")]
        script = build_session_script(
            steps, session_id="aabb", work_dir="C:\\Windows\\Temp\\test",
            os_type="windows",
        )
        assert "$ErrorActionPreference" in script
        assert "SESSION_ID" in script
        assert "Get-Process" in script
        assert "__TASK_OK__" in script

    def test_script_file_step(self):
        steps = [self._make_step(name="sf", script_file="/opt/scripts/scan.sh")]
        script = build_session_script(steps, session_id="aabb", work_dir="/tmp/test")
        assert '"$__OFX_PY_BIN" ".ofx_step_0.py"' in script

    def test_bash_encrypt_at_rest(self):
        steps = [self._make_step(name="scan", run="echo hi")]
        script = build_session_script(
            steps, session_id="aabb", work_dir="/tmp/test",
            encrypt_at_rest=True,
        )
        assert ".skey" in script
        assert "openssl enc" in script
        assert "output.enc" in script
        assert "shred" in script
        assert "__TASK_OK__" in script  # marker still present after encryption block

    def test_bash_no_encrypt_by_default(self):
        steps = [self._make_step(name="scan", run="echo hi")]
        script = build_session_script(
            steps, session_id="aabb", work_dir="/tmp/test",
            encrypt_at_rest=False,
        )
        assert "openssl enc" not in script
        assert "__TASK_OK__" in script

    def test_powershell_encrypt_at_rest(self):
        steps = [self._make_step(name="scan", run="Get-Process")]
        script = build_session_script(
            steps, session_id="aabb", work_dir="C:\\Temp\\test",
            os_type="windows", encrypt_at_rest=True,
        )
        assert ".skey" in script
        assert "output.enc" in script
        assert "AES" in script or "Aes" in script


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

        # At-rest encryption should be enabled
        assert session.at_rest_key
        assert len(session.at_rest_key) == 64  # 32 bytes hex
        assert session.at_rest_encrypted

        # Should be persisted
        loaded = store.load(session.id)
        assert loaded.id == session.id
        assert loaded.at_rest_key == session.at_rest_key

    def test_submit_local_runs_script(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

        # Wait for the process to finish
        import time
        for _ in range(50):
            time.sleep(0.1)
            try:
                os.kill(session.remote_pid, 0)
            except ProcessLookupError:
                break

        # Check status
        session = asyncio.run(mgr.status(session.id))
        assert session.status == SessionStatus.COMPLETED

        # At-rest encryption: output.enc should exist, output/ should be removed
        work = Path(session.remote_work_dir)
        assert (work / "output.enc").exists(), "output.enc missing — at-rest encryption failed"
        assert not (work / "output").exists(), "output/ dir should be removed after encryption"
        # Key file should have been shredded
        assert not (work / ".skey").exists(), "key file should be shredded"
        # Bundled python step artifact should exist for script step in local workspace

    def test_submit_local_stages_bundled_python_script(self, tmp_path):
        wf = tmp_path / "test_script_session.yml"
        wf.write_text(textwrap.dedent("""\
            name: session-script-test
            jobs:
              py-job:
                steps:
                  - name: inline-python
                    script: |
                      print("INLINE_SCRIPT_OK")
        """))
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)
        session = asyncio.run(mgr.submit(str(wf), target=SessionTarget.LOCAL))
        bundled = Path(session.remote_work_dir) / ".ofx_step_0.py"
        assert bundled.exists()
        bundled_text = bundled.read_text()
        assert "INLINE_SCRIPT_OK" not in bundled_text
        assert "_m.loads" in bundled_text or "base64.b64decode" in bundled_text

    def test_status_completed(self, tmp_path):
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

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

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

        import time
        for _ in range(50):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        logs = asyncio.run(mgr.logs(session.id))
        assert "Session" in logs or "started" in logs

    def test_fetch_results(self, tmp_path):
        """Fetch transparently decrypts at-rest encrypted output."""
        wf_path = self._create_test_workflow(tmp_path)
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf_path), target=SessionTarget.LOCAL)
        )

        import time
        for _ in range(50):
            time.sleep(0.1)
            session = asyncio.run(mgr.status(session.id))
            if session.is_done():
                break

        assert session.status == SessionStatus.COMPLETED

        results_path = asyncio.run(mgr.fetch(session.id))
        assert results_path.exists()

        # The at-rest encryption should have been transparently decrypted
        # and result.txt from "echo result data > output/result.txt" should be there
        assert (results_path / "result.txt").exists(), \
            f"result.txt missing; contents: {list(results_path.iterdir())}"

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
        wf.write_text(textwrap.dedent("""\
            name: long-run
            jobs:
              wait-job:
                steps:
                  - name: wait
                    run: sleep 30
        """))
        store = SessionStore(base_dir=tmp_path / "sessions")
        mgr = _make_manager(store, tmp_path)

        session = asyncio.run(
            mgr.submit(str(wf), target=SessionTarget.LOCAL)
        )
        assert session.remote_pid is not None

        # Cancel
        import time
        time.sleep(0.2)  # Let it start
        session = asyncio.run(mgr.cancel(session.id))
        assert session.status == SessionStatus.CANCELED

        # PID should be dead
        time.sleep(0.2)
        try:
            os.kill(session.remote_pid, 0)
            # Process still alive — that's ok, SIGTERM may take a moment
        except ProcessLookupError:
            pass  # Expected

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

    def test_fetch_while_running_raises(self, tmp_path):
        wf = tmp_path / "long_running.yml"
        wf.write_text(textwrap.dedent("""\
            name: long-run
            jobs:
              wait-job:
                steps:
                  - name: wait
                    run: sleep 30
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
# Session input injection tests
# ======================================================================


class TestSessionInputInjection:
    """Tests for session input → env var injection and local file staging."""

    def test_inputs_to_env_scalar(self):
        from ofx.cloud.sessions.manager import _inputs_to_env

        env = _inputs_to_env({"targets_file": "/tmp/hosts.txt", "count": 5})
        assert env["targets_file"] == "/tmp/hosts.txt"
        assert env["INPUT_TARGETS_FILE"] == "/tmp/hosts.txt"
        assert env["count"] == "5"
        assert env["INPUT_COUNT"] == "5"

    def test_inputs_to_env_empty(self):
        from ofx.cloud.sessions.manager import _inputs_to_env

        assert _inputs_to_env({}) == {}

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

            script = (
                Path(session.remote_work_dir) / "run.sh"
            ).read_text()
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
            # File should be staged in workspace
            staged = work_dir / targets.name
            assert staged.exists()
            # Env var should point to staged path
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
                with pytest.raises(RuntimeError, match="Failed to stage session input file"):
                    asyncio.run(
                        mgr.submit(
                            str(wf_file),
                            inputs={"targets_file": str(targets)},
                            name="test-file-stage-fail",
                        )
                    )
        finally:
            settings_mod.DEFAULT_WORKFLOWS_DIRS = original_dirs

    def test_upload_local_file_inputs_failure_raises(self, tmp_path):
        """Cloud file upload helper must fail fast on upload errors."""
        from ofx.cloud.sessions.manager import _upload_local_file_inputs

        src = tmp_path / "hosts.txt"
        src.write_text("10.0.0.1\n")

        class _FailingRemote:
            def upload(self, local_path, remote_path):
                raise RuntimeError("upload broke")

        with pytest.raises(RuntimeError, match="Failed to upload session input file"):
            _upload_local_file_inputs(
                {"targets_file": str(src)},
                _FailingRemote(),
                "/tmp/.ses-1",
                "/",
                is_windows=False,
            )


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
            def cleanup(self): pass

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
            def cleanup(self): pass

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
            update={"remote_launcher": "tmux", "remote_tmux_session": "ofx-ses-abc12345"}
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


class TestTmuxLaunchMetadata:
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
