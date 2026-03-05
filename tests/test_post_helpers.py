from __future__ import annotations

import subprocess
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ofx.api.exploitation.webshell.client import WebShellClient
from ofx.api.post import (
    PostRunnerBase,
    PostSSH,
    PostWebShell,
    deploy_and_run,
    download_via_scp,
    upload_via_scp,
)
from ofx.api.post.enum import (
    bundled_tool_path,
    linpeas_command,
    linux_exploit_suggester_command,
    winpeas_command,
)


# Create a concrete runner for testing (since PostRunnerBase is abstract)
class InTestRunner(PostRunnerBase):
    """Concrete runner for testing purposes."""

    def __init__(self, run_fn, interactive_fn=None):
        self._run_fn = run_fn
        self._interactive_fn = interactive_fn

    def run(self, command: str) -> str:
        return self._run_fn(command)

    def supports_interactive(self) -> bool:
        return self._interactive_fn is not None

    def interactive_shell(self, **kwargs) -> None:
        if self._interactive_fn is None:
            raise NotImplementedError("Interactive shell not supported")
        return self._interactive_fn(**kwargs)


def test_enum_prefers_local(tmp_path):
    local = tmp_path / "linpeas.sh"
    local.write_text("x")
    cmd = linpeas_command(local_path=local, dest="/tmp/linpeas.sh")
    assert "DownloadFile" not in cmd
    assert "curl" not in cmd
    assert "wget" not in cmd

    missing = tmp_path / "missing.sh"
    cmd = linux_exploit_suggester_command(local_path=missing, dest="/tmp/les.sh")
    assert "curl" in cmd or "wget" in cmd

    win_cmd = winpeas_command(local_path=missing, dest="C:\\Temp\\winpeas.exe")
    assert "powershell" in win_cmd.lower()

    assert bundled_tool_path("linpeas.sh").as_posix().endswith("/data/post/linpeas.sh")


def test_post_runner_helpers():
    outputs = {
        "uname -a": "Linux test",
        "id": "uid=0(root) gid=0(root)",
        "whoami": "NT AUTHORITY\\SYSTEM",
    }
    runner = InTestRunner(lambda cmd: outputs[cmd])
    assert runner.detect_os() == "linux"
    assert runner.is_root() is True
    assert runner.is_admin() is True

    win_runner = InTestRunner(lambda cmd: "Windows_NT" if cmd == "uname -a" else "")
    assert (
        "powershell" in win_runner.download_command("http://x", "C:\\Temp\\a").lower()
    )


def test_post_runner_interactive():
    runner = InTestRunner(lambda cmd: "")
    with pytest.raises(NotImplementedError):
        runner.interactive_shell()

    called = {}

    def _interactive(**kwargs):
        called["ok"] = kwargs.get("ok")

    runner = InTestRunner(lambda cmd: "", _interactive)
    runner.interactive_shell(ok=True)
    assert called["ok"] is True


def _make_channel(exit_code=0, stdout=b"ok", stderr=b""):
    """Build mock stdout/stderr channel objects for paramiko exec_command."""
    ch = MagicMock()
    ch.recv_exit_status.return_value = exit_code

    out = MagicMock()
    out.read.return_value = stdout
    out.channel = ch

    err = MagicMock()
    err.read.return_value = stderr

    return ch, out, err


@patch("paramiko.SSHClient")
def test_postssh_run_success(mock_ssh_cls):
    mock_client = MagicMock()
    mock_ssh_cls.return_value = mock_client

    transport = MagicMock()
    transport.is_active.return_value = True
    mock_client.get_transport.return_value = transport

    ch, out, err = _make_channel(exit_code=0, stdout=b"ok", stderr=b"")
    mock_client.exec_command.return_value = (None, out, err)

    runner = PostSSH(
        "host", user="root", port=2222, identity_file="/dev/null"
    )
    # Bypass key loading
    with patch.object(PostSSH, "_load_key", return_value=MagicMock()):
        assert runner.run("whoami") == "ok"

    mock_client.exec_command.assert_called_once()
    call_args = mock_client.exec_command.call_args
    assert call_args[0][0] == "whoami"


@patch("paramiko.SSHClient")
def test_postssh_run_failure(mock_ssh_cls):
    mock_client = MagicMock()
    mock_ssh_cls.return_value = mock_client

    transport = MagicMock()
    transport.is_active.return_value = True
    mock_client.get_transport.return_value = transport

    ch, out, err = _make_channel(exit_code=1, stdout=b"", stderr=b"boom")
    mock_client.exec_command.return_value = (None, out, err)

    runner = PostSSH("host")
    with pytest.raises(RuntimeError):
        runner.run("id")


@patch("paramiko.SSHClient")
def test_postssh_upload_download(mock_ssh_cls, tmp_path):
    mock_client = MagicMock()
    mock_ssh_cls.return_value = mock_client

    transport = MagicMock()
    transport.is_active.return_value = True
    mock_client.get_transport.return_value = transport

    mock_sftp = MagicMock()
    mock_sftp.stat.return_value = True
    mock_client.open_sftp.return_value = mock_sftp

    local = tmp_path / "payload.bin"
    local.write_text("x")

    runner = PostSSH("host", user="root", port=2222)
    runner.upload(str(local), "/tmp/payload.bin")
    mock_sftp.put.assert_called_once_with(str(local), "/tmp/payload.bin")

    runner.download("/tmp/payload.bin", str(local))
    mock_sftp.get.assert_called_once_with("/tmp/payload.bin", str(local))


def test_deploy_and_run_webshell(tmp_path):
    """Test deploy_and_run with a webshell runner."""
    calls = {"upload": []}

    client = WebShellClient.__new__(WebShellClient)

    def fake_upload(local, remote):
        calls["upload"].append((local, remote))
        return "ok"

    def fake_run(cmd):
        return f"ran {cmd}"

    client.upload_file = fake_upload
    client.run_command = fake_run

    webshell_runner = PostWebShell(client)
    local = tmp_path / "tool.bin"
    local.write_text("x")

    result = deploy_and_run(webshell_runner, str(local), "/tmp/tool.bin")
    assert result == "ran /tmp/tool.bin"
    assert calls["upload"] == [(str(local), "/tmp/tool.bin")]


@patch("paramiko.SSHClient")
def test_deploy_and_run_ssh(mock_ssh_cls, tmp_path):
    """Test deploy_and_run with SSH runner."""
    mock_client = MagicMock()
    mock_ssh_cls.return_value = mock_client

    transport = MagicMock()
    transport.is_active.return_value = True
    mock_client.get_transport.return_value = transport

    mock_sftp = MagicMock()
    mock_sftp.stat.return_value = True
    mock_client.open_sftp.return_value = mock_sftp

    ch, out, err = _make_channel(exit_code=0, stdout=b"ran command", stderr=b"")
    mock_client.exec_command.return_value = (None, out, err)

    local = tmp_path / "ssh_tool.bin"
    local.write_text("x")

    ssh_runner = PostSSH("host", user="root")
    result = deploy_and_run(ssh_runner, str(local), "/tmp/ssh.bin", exec_cmd="runme")

    assert "ran" in result
    mock_sftp.put.assert_called_once()  # Upload was called


@patch("paramiko.SSHClient")
def test_transfer_scp_compat(mock_ssh_cls, tmp_path):
    """Test deprecated upload_via_scp / download_via_scp still work."""
    mock_client = MagicMock()
    mock_ssh_cls.return_value = mock_client

    transport = MagicMock()
    transport.is_active.return_value = True
    mock_client.get_transport.return_value = transport

    mock_sftp = MagicMock()
    mock_sftp.stat.return_value = True
    mock_client.open_sftp.return_value = mock_sftp

    local = tmp_path / "payload.bin"
    local.write_text("x")

    upload_via_scp(str(local), "/tmp/payload.bin", "host", user="root", port=2222)
    mock_sftp.put.assert_called_once()

    download_via_scp("/tmp/payload.bin", str(local), "host", user="root", port=2222)
    mock_sftp.get.assert_called_once()
