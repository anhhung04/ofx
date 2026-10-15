"""Tests for the generalized tool installer: binary download, plan mode, guide."""

from __future__ import annotations

import hashlib
import io
import tarfile
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ofx.models.tools import ToolConfig
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.install_guide import render_install_guide
from ofx.runner.tool_installer import (
    ToolInstallation,
    ToolInstallerRunner,
    ToolInstallStep,
    _host_platform,
)


class TestToolConfigModel:
    def test_defaults(self):
        cfg = ToolConfig()
        assert cfg.install == ""
        assert cfg.url == ""
        assert cfg.sha256 == ""
        assert cfg.version == "latest"
        assert cfg.method == "auto"
        assert cfg.install_guide == ""

    def test_string_coerced_by_runner(self):
        # The runner converts bare strings to {"install": str} before validation
        cfg = ToolConfig.model_validate({"install": "apt install nmap"})
        assert cfg.install == "apt install nmap"

    def test_binary_fields(self):
        cfg = ToolConfig(
            url="https://example.com/{os}/{arch}/tool-{version}",
            sha256="abc123",
            version="1.2.3",
            archive_path="bin/tool",
        )
        assert cfg.url == "https://example.com/{os}/{arch}/tool-{version}"
        assert cfg.sha256 == "abc123"


class TestHostPlatform:
    def test_returns_normalized_os_arch(self):
        os_name, arch = _host_platform()
        assert os_name in ("linux", "darwin", "windows")
        assert isinstance(arch, str)
        assert arch  # non-empty


class TestResolveUrl:
    def test_placeholders_substituted(self):
        runner = ToolInstallerRunner(tools={}, ctx=RunContext())
        cfg = ToolConfig(
            url="https://dl.example.com/{os}/{arch}/tool-{version}",
            version="2.0",
        )
        url = runner._resolve_url(cfg)
        os_name, arch = _host_platform()
        assert url == f"https://dl.example.com/{os_name}/{arch}/tool-2.0"

    def test_no_placeholders_unchanged(self):
        runner = ToolInstallerRunner(tools={}, ctx=RunContext())
        cfg = ToolConfig(url="https://example.com/tool")
        assert runner._resolve_url(cfg) == "https://example.com/tool"


class TestPlanOnlyMode:
    @pytest.mark.asyncio
    async def test_missing_tool_recorded_not_installed(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "ofx.runner.tool_installer.TOOLS_BIN_DIR", tmp_path / "tools"
        )
        monkeypatch.setattr("ofx.runner.tool_installer.shutil.which", lambda _: None)

        installer = ToolInstallerRunner(
            tools={"nmap": {"install": "apt install nmap"}},
            ctx=RunContext(),
            plan_only=True,
            show_console=False,
        )
        result = await installer.run()

        assert result.status == RunnerStatus.COMPLETED
        assert installer.missing_tools == ["nmap"]
        assert len(installer.planned_steps) == 1
        assert installer.planned_steps[0].strategy == "shell"
        assert installer.planned_steps[0].command == "apt install nmap"

    @pytest.mark.asyncio
    async def test_installed_tool_skipped_in_plan_mode(self, tmp_path, monkeypatch):
        tool = tmp_path / "tools" / "nmap"
        tool.parent.mkdir(parents=True)
        tool.write_text("#!/bin/sh\n")
        tool.chmod(0o755)
        monkeypatch.setattr(
            "ofx.runner.tool_installer.TOOLS_BIN_DIR", tmp_path / "tools"
        )

        installer = ToolInstallerRunner(
            tools={"nmap": {"install": "apt install nmap"}},
            ctx=RunContext(),
            plan_only=True,
            show_console=False,
        )
        await installer.run()

        assert installer.missing_tools == []
        assert installer.skipped_count == 1

    @pytest.mark.asyncio
    async def test_binary_strategy_planned_with_url(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "ofx.runner.tool_installer.TOOLS_BIN_DIR", tmp_path / "tools"
        )
        monkeypatch.setattr("ofx.runner.tool_installer.shutil.which", lambda _: None)

        installer = ToolInstallerRunner(
            tools={
                "ffuf": {
                    "url": "https://github.com/ffuf/ffuf/releases/download/v{version}/ffuf_{version}_{os}_{arch}.tar.gz",
                    "version": "2.1.0",
                    "sha256": "deadbeef",
                }
            },
            ctx=RunContext(),
            plan_only=True,
            show_console=False,
        )
        await installer.run()

        step = installer.planned_steps[0]
        assert step.strategy == "binary"
        assert "ffuf" in step.command
        assert "sha256: deadbeef" in step.detail

    @pytest.mark.asyncio
    async def test_manual_strategy_when_no_install_or_url(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "ofx.runner.tool_installer.TOOLS_BIN_DIR", tmp_path / "tools"
        )
        monkeypatch.setattr("ofx.runner.tool_installer.shutil.which", lambda _: None)

        installer = ToolInstallerRunner(
            tools={"custom": {"install_guide": "Build from source: make install"}},
            ctx=RunContext(),
            plan_only=True,
            show_console=False,
        )
        await installer.run()

        assert installer.planned_steps[0].strategy == "manual"
        assert "make install" in installer.planned_steps[0].command


class TestBinaryDownload:
    @pytest.mark.asyncio
    async def test_download_and_install_binary(self, monkeypatch, tmp_path):
        tools_dir = tmp_path / "tools"
        monkeypatch.setattr("ofx.runner.tool_installer.TOOLS_BIN_DIR", tools_dir)
        monkeypatch.setattr("ofx.runner.tool_installer.shutil.which", lambda _: None)

        payload = b"#!/bin/sh\necho hello\n"
        sha = hashlib.sha256(payload).hexdigest()

        mock_response = MagicMock()
        mock_response.content = payload
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            installer = ToolInstallerRunner(
                tools={
                    "mytool": {
                        "url": "https://example.com/mytool",
                        "sha256": sha,
                    }
                },
                ctx=RunContext(),
                show_console=False,
            )
            result = await installer.run()

        assert result.status == RunnerStatus.COMPLETED
        assert installer.installed_count == 1
        dest = tools_dir / "mytool"
        assert dest.exists()
        assert dest.read_bytes() == payload
        assert dest.stat().st_mode & 0o111  # executable

    @pytest.mark.asyncio
    async def test_sha256_mismatch_fails(self, monkeypatch, tmp_path):
        tools_dir = tmp_path / "tools"
        monkeypatch.setattr("ofx.runner.tool_installer.TOOLS_BIN_DIR", tools_dir)
        monkeypatch.setattr("ofx.runner.tool_installer.shutil.which", lambda _: None)

        mock_response = MagicMock()
        mock_response.content = b"bad payload"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            installer = ToolInstallerRunner(
                tools={
                    "mytool": {
                        "url": "https://example.com/mytool",
                        "sha256": "0" * 64,
                        "method": "binary",
                    }
                },
                ctx=RunContext(),
                show_console=False,
            )
            await installer.run()

        assert installer.failed_count == 1
        assert not (tools_dir / "mytool").exists()

    @pytest.mark.asyncio
    async def test_archive_extraction(self, monkeypatch, tmp_path):
        tools_dir = tmp_path / "tools"
        monkeypatch.setattr("ofx.runner.tool_installer.TOOLS_BIN_DIR", tools_dir)
        monkeypatch.setattr("ofx.runner.tool_installer.shutil.which", lambda _: None)

        binary_content = b"#!/bin/sh\necho archived\n"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(name="bin/mytool")
            info.size = len(binary_content)
            tf.addfile(info, io.BytesIO(binary_content))
        payload = buf.getvalue()

        mock_response = MagicMock()
        mock_response.content = payload
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            installer = ToolInstallerRunner(
                tools={
                    "mytool": {
                        "url": "https://example.com/mytool.tar.gz",
                        "archive_path": "bin/mytool",
                    }
                },
                ctx=RunContext(),
                show_console=False,
            )
            result = await installer.run()

        assert result.status == RunnerStatus.COMPLETED
        assert (tools_dir / "mytool").read_bytes() == binary_content

    @pytest.mark.asyncio
    async def test_zip_archive_extraction(self, monkeypatch, tmp_path):
        tools_dir = tmp_path / "tools"
        monkeypatch.setattr("ofx.runner.tool_installer.TOOLS_BIN_DIR", tools_dir)
        monkeypatch.setattr("ofx.runner.tool_installer.shutil.which", lambda _: None)

        binary_content = b"#!/bin/sh\necho zipped\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mytool", binary_content)
        payload = buf.getvalue()

        mock_response = MagicMock()
        mock_response.content = payload
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            installer = ToolInstallerRunner(
                tools={
                    "mytool": {
                        "url": "https://example.com/mytool.zip",
                        "archive_path": "mytool",
                    }
                },
                ctx=RunContext(),
                show_console=False,
            )
            await installer.run()

        assert installer.installed_count == 1
        assert (tools_dir / "mytool").read_bytes() == binary_content

    @pytest.mark.asyncio
    async def test_binary_fallback_to_shell_on_failure(self, monkeypatch, tmp_path):
        tools_dir = tmp_path / "tools"
        monkeypatch.setattr("ofx.runner.tool_installer.TOOLS_BIN_DIR", tools_dir)
        monkeypatch.setattr("ofx.runner.tool_installer.shutil.which", lambda _: None)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("network down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def _fake_shell(_self, cmd, env):
            return 0, "installed via shell", ""

        monkeypatch.setattr(
            "ofx.runner.tool_installer.ToolInstallerRunner._run_shell", _fake_shell
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            installer = ToolInstallerRunner(
                tools={
                    "mytool": {
                        "url": "https://example.com/mytool",
                        "install": "apt install mytool",
                        "method": "auto",
                    }
                },
                ctx=RunContext(),
                show_console=False,
            )
            result = await installer.run()

        assert result.status == RunnerStatus.COMPLETED
        assert installer.installed_count == 1


class TestRemoteInstall:
    def test_install_remotely_builds_curl_command(self):
        installer = ToolInstallerRunner(tools={}, ctx=RunContext())
        remote = MagicMock()
        remote.run = MagicMock(return_value=0)

        ok = installer.install_remotely(
            remote,
            "nmap",
            {"url": "https://example.com/nmap-{os}-{arch}"},
        )

        assert ok is True
        cmd = remote.run.call_args[0][0]
        assert "curl" in cmd
        assert "chmod +x" in cmd
        assert "nmap" in cmd

    def test_install_remotely_with_sha256(self):
        installer = ToolInstallerRunner(tools={}, ctx=RunContext())
        remote = MagicMock()
        remote.run = MagicMock(return_value=0)

        installer.install_remotely(
            remote,
            "tool",
            {"url": "https://example.com/tool", "sha256": "abc123"},
        )

        cmd = remote.run.call_args[0][0]
        assert "sha256sum -c" in cmd
        assert "abc123" in cmd

    def test_install_remotely_no_url_returns_false(self):
        installer = ToolInstallerRunner(tools={}, ctx=RunContext())
        remote = MagicMock()

        ok = installer.install_remotely(remote, "tool", {"install": "apt install tool"})
        assert ok is False
        remote.run.assert_not_called()

    def test_install_remotely_failure_returns_false(self):
        installer = ToolInstallerRunner(tools={}, ctx=RunContext())
        remote = MagicMock()
        remote.run = MagicMock(side_effect=ConnectionError("ssh failed"))

        ok = installer.install_remotely(
            remote, "tool", {"url": "https://example.com/tool"}
        )
        assert ok is False


class TestInstallGuide:
    def test_renders_all_strategies(self, capsys):
        steps = [
            ToolInstallStep(
                tool="nmap", strategy="shell", command="apt install nmap"
            ),
            ToolInstallStep(
                tool="ffuf",
                strategy="binary",
                command="https://github.com/ffuf/releases/ffuf",
                detail="sha256: abc",
            ),
            ToolInstallStep(
                tool="custom",
                strategy="manual",
                command="Build from source: make install",
            ),
        ]
        render_install_guide(steps)
        out = capsys.readouterr().out
        assert "nmap" in out
        assert "ffuf" in out
        assert "custom" in out
        assert "--install-tools" in out

    def test_empty_steps_no_output(self, capsys):
        render_install_guide([])
        out = capsys.readouterr().out
        assert out == ""


class TestToolInstallStep:
    def test_model_fields(self):
        step = ToolInstallStep(
            tool="nmap", strategy="shell", command="apt install nmap"
        )
        assert step.tool == "nmap"
        assert step.strategy == "shell"
        assert step.detail == ""


class TestToolInstallation:
    def test_plan_only_field(self):
        model = ToolInstallation(tools={"nmap": "apt install nmap"}, plan_only=True)
        assert model.plan_only is True
        assert "nmap" in model.tools
