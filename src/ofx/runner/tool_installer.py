"""Tool installer runner for installing workflow tools."""

from __future__ import annotations

import asyncio
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

from ofx.models.tools import ToolConfig
from ofx.runner.context import RunContext
from ofx.runner.runner import Runner
from ofx.settings import DEFAULT_SHELL, TOOLS_BIN_DIR, ensure_dir

console = Console()


def _host_platform() -> tuple[str, str]:
    """Return normalized (os, arch) for URL placeholder substitution."""
    os_name = platform.system().lower()
    machine = platform.machine().lower()
    arch = {
        "x86_64": "amd64",
        "aarch64": "arm64",
        "armv7l": "armv7",
    }.get(machine, machine)
    return os_name, arch


class ToolInstallStep(BaseModel):
    """A single planned install action, used for the install guide UI."""

    tool: str
    strategy: str  # "binary" | "shell" | "manual"
    command: str  # shell command or download URL
    detail: str = ""  # sha256, archive path, or human guide text


class ToolInstallation(BaseModel):
    """Model for tool installation configuration."""

    tools: dict[str, str | dict[str, Any] | ToolConfig] = Field(
        default_factory=dict,
        description="Tools to install with their configurations",
    )
    show_console: bool = Field(
        default=True,
        description="Whether to show console output during installation",
    )
    plan_only: bool = Field(
        default=False,
        description="Collect install steps without executing (guide mode)",
    )


class ToolInstallerRunner(Runner[ToolInstallation]):
    """Runner for installing tools with template resolution support."""

    def __init__(
        self,
        tools: Mapping[str, str | dict[str, Any] | ToolConfig],
        ctx: RunContext,
        parent: Runner | None = None,
        show_console: bool = True,
        plan_only: bool = False,
    ):
        tool_model = ToolInstallation(
            tools=dict(tools),
            show_console=show_console,
            plan_only=plan_only,
        )
        super().__init__(
            tool_model,
            ctx,
            parent,
            parent.registry if parent is not None else None,
        )
        self.installed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.planned_steps: list[ToolInstallStep] = []
        self.missing_tools: list[str] = []

    def _produce_log(self, message: str) -> str:
        """Produce a log message."""
        return f"[ToolInstaller] {message}"

    async def _run_shell(self, cmd: str, env: Mapping[str, Any]) -> tuple[int, str, str]:
        """Run *cmd* in a shell, returning ``(exit_code, stdout, stderr)``."""
        env_with_path = {
            **os.environ,
            **{str(key): str(value) for key, value in env.items()},
        }
        # Lazy: keeps the runner → modules direction acyclic at import time.
        from ofx.modules.builtins.shell import get_shell_functions

        completed = await asyncio.to_thread(
            subprocess.run,
            f"{get_shell_functions()}\n{cmd}",
            shell=True,
            executable=DEFAULT_SHELL,
            env=env_with_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr

    def _resolve_url(self, config: ToolConfig) -> str:
        """Substitute platform/version placeholders into the download URL."""
        os_name, arch = _host_platform()
        return (
            config.url
            .replace("{os}", os_name)
            .replace("{arch}", arch)
            .replace("{version}", config.version)
        )

    async def _download_binary(self, tool_bin: str, config: ToolConfig) -> Path:
        """Download and install a prebuilt binary. Returns the installed path."""
        import httpx

        url = self._resolve_url(config)
        dest = TOOLS_BIN_DIR / tool_bin
        ensure_dir(TOOLS_BIN_DIR)

        async def _fetch() -> bytes:
            async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content

        payload = await _fetch()

        if config.sha256:
            digest = hashlib.sha256(payload).hexdigest()
            if digest.lower() != config.sha256.lower():
                raise RuntimeError(
                    f"SHA-256 mismatch for {tool_bin}: "
                    f"expected {config.sha256}, got {digest}"
                )

        if config.archive_path:
            import io

            if zipfile.is_zipfile(io.BytesIO(payload)):
                with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                    data = zf.read(config.archive_path)
            else:
                with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as tf:
                    member = tf.extractfile(config.archive_path)
                    if member is None:
                        raise RuntimeError(
                            f"'{config.archive_path}' not found in archive for {tool_bin}"
                        )
                    data = member.read()
            payload = data

        dest.write_bytes(payload)
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return dest

    async def _do_run(self) -> None:
        """Install all configured tools (or just plan them in plan_only mode)."""
        if not self.model.tools:
            return

        current_path = self.ctx.envs.get("PATH", os.environ.get("PATH", ""))
        if str(TOOLS_BIN_DIR) not in current_path:
            ensure_dir(TOOLS_BIN_DIR)
            self.update_env({"PATH": f"{TOOLS_BIN_DIR}:{current_path}"})

        for tool_bin, tool_config in self.model.tools.items():
            await self._install_tool(tool_bin, tool_config)

    def _plan_step(self, tool_bin: str, config: ToolConfig) -> ToolInstallStep:
        """Build the install step a user would run manually."""
        if config.url and config.method in ("auto", "binary"):
            url = self._resolve_url(config)
            detail = f"sha256: {config.sha256}" if config.sha256 else ""
            if config.archive_path:
                detail = f"{detail} extract: {config.archive_path}".strip()
            return ToolInstallStep(tool=tool_bin, strategy="binary", command=url, detail=detail)
        if config.install and config.method in ("auto", "shell"):
            return ToolInstallStep(tool=tool_bin, strategy="shell", command=config.install)
        guide = config.install_guide or f"Install '{tool_bin}' manually and ensure it is on PATH"
        return ToolInstallStep(tool=tool_bin, strategy="manual", command=guide, detail="")

    async def _install_tool(
        self,
        tool_bin: str,
        tool_config: str | dict[str, Any] | ToolConfig,
    ) -> None:
        """Install a single tool (or record its plan in plan_only mode)."""
        if isinstance(tool_config, str):
            tool_config = {"install": tool_config}

        config = ToolConfig.model_validate(tool_config)

        check_cmd = (
            await self._resolve_template(config.check) if config.check else None
        )

        if check_cmd:
            self._log_debug(f"Checking tool '{tool_bin}' with: {check_cmd}")
            check_exit, _check_stdout, _check_stderr = await self._run_shell(
                check_cmd,
                self.ctx.envs,
            )
            exists = check_exit == 0
        else:
            tool_path = TOOLS_BIN_DIR / tool_bin
            exists = tool_path.exists() or shutil.which(tool_bin) is not None
        if exists:
            if self.model.show_console:
                console.print(f"[dim]Skipping {tool_bin} (already installed)[/dim]")
            self._log_debug(f"Tool '{tool_bin}' is already installed, skipping")
            self.skipped_count += 1
            return

        if self.model.plan_only:
            self.missing_tools.append(tool_bin)
            self.planned_steps.append(self._plan_step(tool_bin, config))
            self._log_debug(f"Planned install for '{tool_bin}'")
            return

        # Binary download path (preferred when url is set)
        if config.url and config.method in ("auto", "binary"):
            try:
                if self.model.show_console:
                    console.print(f"[cyan]Downloading {tool_bin}...[/cyan]")
                self._log_info(f"Downloading '{tool_bin}' from {self._resolve_url(config)}")
                dest = await self._download_binary(tool_bin, config)
                if self.model.show_console:
                    console.print(f"[green]✓ Installed {tool_bin} → {dest}[/green]")
                self._log_info(f"Tool '{tool_bin}' installed to {dest}")
                self.installed_count += 1
                await self._run_post_install(tool_bin, config)
                return
            except Exception as exc:
                self._log_warning(
                    f"Binary download for '{tool_bin}' failed: {exc}; "
                    "falling back to shell install"
                )
                if config.method == "binary" or not config.install:
                    if self.model.show_console:
                        console.print(f"[red]✗ Failed to install {tool_bin}: {exc}[/red]")
                    self._log_error(f"Failed to install tool '{tool_bin}': {exc}")
                    self.failed_count += 1
                    return

        # Shell install path
        install_cmd = await self._resolve_template(config.install)
        if not install_cmd:
            self._log_error(f"Tool '{tool_bin}' has no install command or url")
            self.failed_count += 1
            return

        try:
            if self.model.show_console:
                console.print(f"[cyan]Installing {tool_bin}...[/cyan]")
            self._log_info(f"Installing tool '{tool_bin}' with command: {install_cmd}")

            install_exit, install_stdout, install_stderr = await self._run_shell(
                install_cmd,
                self.ctx.envs,
            )

            if install_exit != 0:
                error_detail = (install_stderr or install_stdout or "").strip()
                error_msg = (
                    f"Failed to install tool '{tool_bin}': {error_detail}"
                    if error_detail
                    else f"Failed to install tool '{tool_bin}' (exit {install_exit})"
                )
                if self.model.show_console:
                    console.print(
                        f"[red]✗ Failed to install {tool_bin}: {error_detail}[/red]"
                    )
                self._log_error(error_msg)
                self.failed_count += 1
                return

            if self.model.show_console:
                console.print(f"[green]✓ Successfully installed {tool_bin}[/green]")
            self._log_info(f"Tool '{tool_bin}' installed successfully")
            self.installed_count += 1
            await self._run_post_install(tool_bin, config)

        except Exception as exc:
            if self.model.show_console:
                console.print(f"[red]✗ Error installing {tool_bin}: {exc}[/red]")
            self._log_error(f"Error installing tool '{tool_bin}': {exc}")
            self.failed_count += 1

    def install_remotely(
        self,
        remote_runner: Any,
        tool_bin: str,
        tool_config: str | dict[str, Any] | ToolConfig,
        *,
        remote_tools_dir: str = "/tmp/.ofx-tools",
    ) -> bool:
        """Install a tool on a remote host via its runner's ``run`` method.

        Only the binary-download strategy is supported remotely (no package
        manager assumptions). Returns True on success.
        """
        if isinstance(tool_config, str):
            tool_config = {"install": tool_config}
        config = ToolConfig.model_validate(tool_config)

        if not config.url:
            self._log_warning(
                f"Remote install for '{tool_bin}' requires a prebuilt binary url; "
                "shell install is not supported remotely"
            )
            return False

        url = self._resolve_url(config)
        dest = f"{remote_tools_dir}/{tool_bin}"
        cmd = (
            f"mkdir -p {remote_tools_dir} && "
            f"curl -fSsL {url!r} -o {dest} && chmod +x {dest}"
        )
        if config.sha256:
            cmd += f' && echo "{config.sha256}  {dest}" | sha256sum -c -'
        if config.archive_path:
            cmd += (
                f" && cd {remote_tools_dir} && "
                f"(unzip -o {dest} {config.archive_path} || "
                f"tar -xf {dest} {config.archive_path}) && "
                f"mv {config.archive_path} {dest}"
            )
        try:
            result = remote_runner.run(cmd)
            rc = result if isinstance(result, int) else getattr(result, "returncode", 0)
            return rc == 0
        except Exception as exc:
            self._log_warning(f"Remote install of '{tool_bin}' failed: {exc}")
            return False

    async def _run_post_install(self, tool_bin: str, config: ToolConfig) -> None:
        """Run the optional post-install command."""
        if not config.post_install:
            return
        post_install_cmd = await self._resolve_template(config.post_install)
        self._log_info(f"Running post-install for '{tool_bin}'")
        post_exit, post_stdout, post_stderr = await self._run_shell(
            post_install_cmd,
            self.ctx.envs,
        )
        if post_exit == 0:
            if post_stdout.strip():
                self._log_info(
                    f"Post-install output for '{tool_bin}': {post_stdout.strip()}"
                )
        else:
            self._log_warning(
                f"Post-install command for '{tool_bin}' failed "
                f"(exit {post_exit}): {(post_stderr or post_stdout).strip()}"
            )


__all__ = ["ToolInstallStep", "ToolInstallation", "ToolInstallerRunner"]
