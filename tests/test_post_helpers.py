from __future__ import annotations

import subprocess
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ofx.api.exploitation.webshell.client import WebShellClient
from ofx.api.post.enum import (
    bundled_tool_path,
    linpeas_command,
    linux_exploit_suggester_command,
    winpeas_command,
)
from ofx.api.post.remote import PostRunner, PostSSH
from ofx.api.post.transfer_remote import (
    deploy_and_run,
    download_via_scp,
    upload_via_scp,
)


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
    runner = PostRunner(lambda cmd: outputs[cmd])
    assert runner.detect_os() == "linux"
    assert runner.is_root() is True
    assert runner.is_admin() is True

    win_runner = PostRunner(lambda cmd: "Windows_NT" if cmd == "uname -a" else "")
    assert "powershell" in win_runner.download_command("http://x", "C:\\Temp\\a").lower()


def test_post_runner_interactive():
    runner = PostRunner(lambda cmd: "")
    with pytest.raises(RuntimeError):
        runner.interactive_shell()

    called = {}

    def _interactive(**kwargs):
        called["ok"] = kwargs.get("ok")

    runner = PostRunner(lambda cmd: "", _interactive)
    runner.interactive_shell(ok=True)
    assert called["ok"] is True


def test_postssh_run_success(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_run(cmd, text, capture_output, timeout, check):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = PostSSH("host", user="root", port=2222, identity_file="id_rsa", extra_args=["-v"])
    assert runner.run("whoami") == "ok"
    assert captured["cmd"][0] == "ssh"


def test_postssh_run_failure(monkeypatch: pytest.MonkeyPatch):
    def fake_run(cmd, text, capture_output, timeout, check):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = PostSSH("host")
    with pytest.raises(RuntimeError):
        runner.run("id")


def test_transfer_scp_builds_command(monkeypatch: pytest.MonkeyPatch, tmp_path):
    captured = {}

    def fake_run(cmd, text, capture_output, timeout, check):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    local = tmp_path / "payload.bin"
    local.write_text("x")

    upload_via_scp(str(local), "/tmp/payload.bin", "host", user="root", port=2222, identity_file="id_rsa")
    assert captured["cmd"][0] == "scp"
    assert "root@host:/tmp/payload.bin" in captured["cmd"]

    download_via_scp("/tmp/payload.bin", str(local), "host", user="root", port=2222)
    assert captured["cmd"][0] == "scp"
    assert "root@host:/tmp/payload.bin" in captured["cmd"]


def test_deploy_and_run_branches(monkeypatch: pytest.MonkeyPatch, tmp_path):
    calls = {"upload": [], "scp": [], "winrm": []}

    client = WebShellClient.__new__(WebShellClient)

    def fake_upload(local, remote):
        calls["upload"].append((local, remote))
        return "ok"

    client.upload_file = fake_upload

    webshell_runner = SimpleNamespace(client=client, run=lambda cmd: f"ran {cmd}")
    local = tmp_path / "tool.bin"
    local.write_text("x")

    result = deploy_and_run(webshell_runner, str(local), "/tmp/tool.bin")
    assert result == "ran /tmp/tool.bin"
    assert calls["upload"] == [(str(local), "/tmp/tool.bin")]

    def fake_scp(local_path, remote_path, host, user, port, identity_file):
        calls["scp"].append((local_path, remote_path, host, user, port, identity_file))

    monkeypatch.setattr(
        "ofx.api.post.transfer_remote.upload_via_scp",
        fake_scp,
    )

    class PostSSH:
        def __init__(self):
            self.host = "host"
            self.user = "root"
            self.port = 22
            self.identity_file = None

        def run(self, command: str) -> str:
            return f"ran {command}"

    ssh_runner = PostSSH()
    result = deploy_and_run(ssh_runner, str(local), "/tmp/ssh.bin", exec_cmd="runme")
    assert result == "ran runme"
    assert calls["scp"]

    def fake_winrm(runner, local_path, remote_path):
        calls["winrm"].append((local_path, remote_path))

    monkeypatch.setattr(
        "ofx.api.post.transfer_remote.upload_via_winrm",
        fake_winrm,
    )

    winrm_runner = SimpleNamespace(run=lambda cmd: f"ran {cmd}")
    result = deploy_and_run(winrm_runner, str(local), "C:\\Temp\\tool.exe")
    assert result == "ran C:\\Temp\\tool.exe"
    assert calls["winrm"] == [(str(local), "C:\\Temp\\tool.exe")]
