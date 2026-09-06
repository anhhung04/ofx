"""Session results: fetch, decrypt, and artifact bundling."""

from __future__ import annotations

import json
import logging
import secrets as _secrets
import shlex
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from ofx.cloud.runtime import remote_join
from ofx.cloud.sessions.encryption import decrypt_results, encrypt_results
from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.utils.file_cleanup import remove_files

logger = logging.getLogger("ofx")

def _decrypt_at_rest_openssl(
    enc_file: Path, at_rest_key: str, output_dir: Path
) -> None:
    """Decrypt an at-rest encrypted archive produced by the session script.

    The session script uses ``openssl enc -aes-256-cbc -pbkdf2`` with the
    key written to a file.  We replicate the same decryption locally.

    Args:
        enc_file: Path to the ``output.enc`` file.
        at_rest_key: The hex key string used for encryption.
        output_dir: Where to extract the decrypted tar.gz contents.
    """
    import tarfile as _tarfile

    output_dir.mkdir(parents=True, exist_ok=True)

    key_path = enc_file.parent / f".dec_{_secrets.token_hex(4)}"
    key_path.write_text(at_rest_key)
    key_path.chmod(0o600)

    tar_path = enc_file.parent / "output_dec.tar.gz"

    try:
        result = subprocess.run(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-iter",
                "100000",
                "-pass",
                f"file:{key_path}",
                "-in",
                str(enc_file),
                "-out",
                str(tar_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            start_new_session=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"openssl decryption failed (rc={result.returncode}): {result.stderr.strip()}"
            )

        with _tarfile.open(str(tar_path), "r:gz") as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts
                if parts and len(parts) > 1 and parts[0] == "output":
                    member.name = str(Path(*parts[1:]))
                elif parts and parts[0] == "output":
                    continue
                tar.extract(member, path=str(output_dir), filter="data")

        logger.debug("At-rest decrypted %s → %s", enc_file, output_dir)
    finally:
        remove_files([path for path in (key_path, tar_path) if path is not None])

class ResultsMixin:
    async def fetch(
        self,
        session_id: str,
        *,
        passphrase: str = "",
        output_dir: Path | None = None,
    ) -> Path:
        """Download results from a completed session.

        If the session has at-rest encryption enabled, the encrypted archive
        is downloaded and transparently decrypted using the stored key before
        results are written to disk.

        Args:
            session_id: Session ID.
            passphrase: If provided, re-encrypt results with this passphrase
                after fetching (user-level encryption).
            output_dir: Override destination directory.

        Returns:
            Path to the results directory (or encrypted file).
        """
        session = await self.status(session_id)

        if session.is_running():
            raise RuntimeError(
                f"Session {session_id} is still running (status={session.status.value}). "
                "Wait for completion or cancel first."
            )

        results = output_dir or self._resolve_results_dir(session)

        if session.target == SessionTarget.LOCAL:
            self._fetch_local_results(session, results)
        else:
            await self._fetch_cloud_results(session, results)
            session = await self._auto_destroy_after_fetch(session)

        if passphrase:
            enc_path = encrypt_results(results, passphrase)
            session = self._save_encrypted_results(
                session,
                encrypted_file=enc_path,
                results=results,
            )
        else:
            session = self._save_fetched_results(session, results)

        return results if not passphrase else Path(session.encrypted_file)
    async def _auto_destroy_after_fetch(self, session: Session) -> Session:
        """Auto-destroy cloud instance after fetch when configured and non-static."""
        if session.target != SessionTarget.CLOUD:
            return session
        if not session.instance_id:
            return session
        if not session.auto_destroy:
            return session
        return await self._destroy_session_instance(
            session,
            clear_instance_fields=True,
            warning_message="Auto-destroy after fetch failed for session %s (instance %s): %s",
        )
    def _fetch_local_results(self, session: Session, results: Path) -> None:
        """Copy local session output to results dir, decrypting if needed."""
        work_dir = Path(session.remote_work_dir)
        self._prepare_results_dir(results)

        enc_file = self._session_encrypted_results_path(work_dir)
        if session.at_rest_encrypted and enc_file.exists():
            _decrypt_at_rest_openssl(enc_file, session.at_rest_key, results)
        else:
            self._copy_output_dir(self._session_output_dir(work_dir), results)

        self._copy_log_file(Path(session.remote_log_file), results)
    async def _fetch_cloud_results(self, session: Session, results: Path) -> None:
        """Download output from a cloud VPS via SCP, decrypting if needed."""
        def _download_results(remote: Any) -> None:
            self._prepare_results_dir(results)

            if self._download_encrypted_results_archive(remote, session, results):
                self._download_remote_log(remote, session, results)
                return

            self._download_remote_output_files(remote, session, results)
            self._download_remote_log(remote, session, results)

        self._with_reconnected_remote(session, _download_results)
    async def decrypt(
        self,
        session_id: str,
        passphrase: str,
        output_dir: Path | None = None,
    ) -> Path:
        """Decrypt previously encrypted session results.

        Returns:
            Path to the decrypted results directory.
        """
        session = self.store.load(session_id)
        if not session.encrypted or not session.encrypted_file:
            raise RuntimeError(f"Session {session_id} results are not encrypted")

        enc_path = Path(session.encrypted_file)
        out = output_dir or self.store.results_dir(session_id) / "decrypted"
        result = decrypt_results(enc_path, passphrase, out)
        return result
    async def bundle_artifacts(
        self,
        session_id: str,
        *,
        output_file: Path | None = None,
        include_project_context: bool = True,
    ) -> Path:
        """Create a tar.gz bundle with session metadata + fetched artifacts."""
        session_dir = self.store.session_dir(session_id)
        session, results_dir = await self._ensure_results_dir(session_id)

        bundle_path = output_file or (session_dir / f"bundle_{session_id}.tar.gz")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        manifest_path = session_dir / f"bundle_manifest_{session.id}.json"
        manifest_path.write_text(json.dumps(self._bundle_manifest(session), indent=2))
        try:
            with tarfile.open(bundle_path, "w:gz") as tf:
                tf.add(manifest_path, arcname="manifest.json")
                tf.add(session_dir / "session.json", arcname="session.json")
                if results_dir.exists():
                    tf.add(results_dir, arcname="results")
                if include_project_context and session.project:
                    self._add_project_logs_to_bundle(tf, session)
        finally:
            remove_files([manifest_path])

        return bundle_path
    async def _ensure_results_dir(self, session_id: str) -> tuple[Session, Path]:
        session = self.store.load(session_id)
        results_dir = Path(session.results_path) if session.results_path else None
        if results_dir is not None and results_dir.exists():
            return session, results_dir

        if session.status in (
            SessionStatus.COMPLETED,
            SessionStatus.FETCHED,
            SessionStatus.ENCRYPTED,
        ):
            await self.fetch(session_id)
            session = self.store.load(session_id)
            results_dir = Path(session.results_path) if session.results_path else None

        if results_dir is None or not results_dir.exists():
            raise RuntimeError(
                f"No fetched results available for session {session_id}. "
                "Run 'ofx session fetch <id>' first."
            )
        return session, results_dir
    def _resolve_results_dir(self, session: Session) -> Path:
        """Resolve where to store fetched results.

        If the session is associated with a project, results go into
        ``<project_path>/evidence/sessions/<session_id>/``.
        Otherwise falls back to ``~/.ofx/sessions/<id>/results/``.
        """
        project_path = self._resolved_project_path(
            session.project,
            error_message="Project evidence path resolution failed: %s",
        )
        if project_path is not None:
            project_results_dir = project_path / "evidence" / "sessions" / session.id
            project_results_dir.mkdir(parents=True, exist_ok=True)
            return project_results_dir
        return self.store.results_dir(session.id)
    @staticmethod
    def _bundle_manifest(session: Session) -> dict[str, Any]:
        return {
            "session_id": session.id,
            "name": session.name,
            "status": session.status.value,
            "target": session.target.value,
            "workflow_file": session.workflow_file,
            "job_id": session.job_id,
            "execution_scope": session.job_id or "full-workflow",
            "project": session.project,
            "started_at": session.started_at.isoformat(),
            "finished_at": session.finished_at.isoformat()
            if session.finished_at
            else None,
            "instance_ip": session.instance_ip,
            "instance_id": session.instance_id,
            "cloud_profile": session.cloud_profile,
            "fleet_group_id": session.fleet_group_id,
            "fleet_index": session.fleet_index,
            "fleet_total": session.fleet_total,
        }
    def _add_project_logs_to_bundle(self, bundle: tarfile.TarFile, session: Session) -> None:
        project_path = self._resolved_project_path(
            session.project,
            error_message="Project log path resolution failed: %s",
        )
        if project_path is None:
            return

        logs_dir = project_path / "logs"
        if not logs_dir.exists():
            return
        bundle.add(logs_dir, arcname="project_logs")
    @staticmethod
    def _resolved_project_path(
        project: str,
        *,
        error_message: str,
    ) -> Path | None:
        if not project:
            return None

        try:
            from ofx.commands.project.project_manager import ProjectManager

            project_path = Path(ProjectManager.resolve_path(project))
        except Exception as exc:
            logger.debug(error_message, exc)
            return None

        if not project_path.exists():
            return None
        return project_path
    @staticmethod
    def _prepare_results_dir(results: Path) -> None:
        results.mkdir(parents=True, exist_ok=True)
    @staticmethod
    def _results_log_path(results: Path) -> Path:
        return results / "output.log"
    @staticmethod
    def _session_encrypted_results_path(work_dir: str | Path) -> Path:
        return Path(work_dir) / "output.enc"
    @staticmethod
    def _session_output_dir(work_dir: str | Path) -> Path:
        return Path(work_dir) / "output"
    @classmethod
    def _copy_output_entry(cls, entry: Path, results: Path) -> None:
        destination = results / entry.name
        if entry.is_file():
            shutil.copy2(str(entry), str(destination))
            return
        if entry.is_dir():
            shutil.copytree(str(entry), str(destination), dirs_exist_ok=True)
    @classmethod
    def _copy_output_dir(cls, output_dir: Path, results: Path) -> None:
        if not output_dir.exists():
            return
        for entry in output_dir.iterdir():
            cls._copy_output_entry(entry, results)
    @classmethod
    def _copy_log_file(cls, log_path: Path, results: Path) -> None:
        if not log_path.exists():
            return
        shutil.copy2(str(log_path), str(cls._results_log_path(results)))
    @staticmethod
    def _remote_encrypted_results_path(session: Session) -> str:
        return remote_join(
            session.remote_work_dir,
            "output.enc",
            is_windows=session.os_type == "windows",
        )
    @staticmethod
    def _remote_output_dir_path(session: Session) -> str:
        return remote_join(
            session.remote_work_dir,
            "output",
            is_windows=session.os_type == "windows",
        )
    @staticmethod
    def _remote_output_file_path(session: Session, filename: str) -> str:
        return remote_join(
            session.remote_work_dir,
            "output",
            filename,
            is_windows=session.os_type == "windows",
        )
    @classmethod
    def _remote_output_list_command(cls, session: Session) -> str:
        output_dir = cls._remote_output_dir_path(session)
        if session.os_type == "windows":
            return (
                f"powershell \"Get-ChildItem -Path '{output_dir}' "
                f'-File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"'
            )
        return f"ls -1 {shlex.quote(str(output_dir))} 2>/dev/null"
    @staticmethod
    def _remote_output_names(output: str) -> list[str]:
        return [line.strip() for line in output.splitlines() if line.strip()]
    @staticmethod
    def _download_optional_remote_file(
        remote: Any,
        remote_path: str,
        local_path: Path,
        *,
        label: str,
    ) -> bool:
        try:
            remote.download(remote_path, str(local_path))
            return True
        except Exception as exc:
            logger.debug("Failed to download %s %s: %s", label, remote_path, exc)
            return False
    def _download_remote_log(
        self,
        remote: Any,
        session: Session,
        results: Path,
    ) -> None:
        self._download_optional_remote_file(
            remote,
            session.remote_log_file,
            self._results_log_path(results),
            label="remote log",
        )
    def _download_remote_output_files(
        self,
        remote: Any,
        session: Session,
        results: Path,
    ) -> None:
        output = remote.run(self._remote_output_list_command(session), timeout=30)
        for filename in self._remote_output_names(output):
            self._download_optional_remote_file(
                remote,
                self._remote_output_file_path(session, filename),
                results / filename,
                label="remote output",
            )
    def _download_encrypted_results_archive(
        self,
        remote: Any,
        session: Session,
        results: Path,
    ) -> bool:
        if not session.at_rest_encrypted:
            return False

        local_archive = results.parent / f"output_{session.id}.enc"
        try:
            remote.download(
                self._remote_encrypted_results_path(session),
                str(local_archive),
            )
        except Exception as exc:
            logger.warning(
                "Encrypted archive not found on VPS (%s); "
                "falling back to unencrypted fetch",
                exc,
            )
            return False

        if not local_archive.exists():
            return False

        try:
            _decrypt_at_rest_openssl(local_archive, session.at_rest_key, results)
            return True
        finally:
            remove_files([local_archive])
    def _save_fetched_results(self, session: Session, results: Path) -> Session:
        return self._save_session(
            session,
            {
                "status": SessionStatus.FETCHED,
                "results_path": str(results),
            },
        )
    def _save_encrypted_results(
        self,
        session: Session,
        *,
        encrypted_file: Path,
        results: Path,
    ) -> Session:
        return self._save_session(
            session,
            {
                "status": SessionStatus.ENCRYPTED,
                "encrypted": True,
                "encrypted_file": str(encrypted_file),
                "results_path": str(results),
            },
        )
