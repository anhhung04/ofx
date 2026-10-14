"""Tool installer runner for installing workflow tools."""

import asyncio
import os
import shutil
import subprocess
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

from ofx.models.workflow import ToolConfig
from ofx.modules.builtins.shell import get_shell_functions
from ofx.runner.context import RunContext
from ofx.runner.runner import Runner
from ofx.settings import DEFAULT_SHELL, TOOLS_BIN_DIR, ensure_dir

console = Console()

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

class ToolInstallerRunner(Runner[ToolInstallation]):
    """Runner for installing tools with template resolution support."""

    def __init__(
        self,
        tools: Mapping[str, str | dict[str, Any] | ToolConfig],
        ctx: RunContext,
        parent: Runner | None = None,
        show_console: bool = True,
    ):
        tool_model = ToolInstallation(
            tools=dict(tools),
            show_console=show_console,
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

    def _produce_log(self, message: str) -> str:
        """Produce a log message."""
        return f"[ToolInstaller] {message}"

    async def _run_shell(self, cmd: str, env: Mapping[str, Any]) -> tuple[int, str, str]:
        """Run *cmd* in a shell, returning ``(exit_code, stdout, stderr)``.

        Replaces the removed ``CommandRunner``: tool install/check commands
        are not module steps, so a plain subprocess suffices (no streaming or
        interactive mode). The shell-helper preamble is prepended so install
        commands can use the ``fapt``/``uv_install``/… helpers, and *env* is
        passed by value so mutations never leak back to the caller's context.
        """
        env_with_path = {
            **os.environ,
            **{str(key): str(value) for key, value in env.items()},
        }
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

    async def _do_run(self) -> None:
        """Install all configured tools."""
        if not self.model.tools:
            return

        current_path = self.ctx.envs.get("PATH", os.environ.get("PATH", ""))
        if str(TOOLS_BIN_DIR) not in current_path:
            ensure_dir(TOOLS_BIN_DIR)
            self.update_env({"PATH": f"{TOOLS_BIN_DIR}:{current_path}"})

        for tool_bin, tool_config in self.model.tools.items():
            await self._install_tool(tool_bin, tool_config)

    async def _install_tool(
        self,
        tool_bin: str,
        tool_config: str | dict[str, Any] | ToolConfig,
    ) -> None:
        """Install a single tool."""
        if isinstance(tool_config, str):
            tool_config = {"install": tool_config}

        tool_config = ToolConfig.model_validate(tool_config)

        install_cmd = await self._resolve_template(tool_config.install)
        check_cmd = (
            await self._resolve_template(tool_config.check)
            if tool_config.check
            else None
        )
        post_install_cmd = (
            await self._resolve_template(tool_config.post_install)
            if tool_config.post_install
            else None
        )

        if check_cmd:
            self._log_debug(f"Checking tool '{tool_bin}' with: {check_cmd}")
            check_exit, _check_stdout, _check_stderr = await self._run_shell(
                check_cmd,
                self.ctx.envs,
            )
            tool_exists = check_exit == 0
        else:
            tool_path = TOOLS_BIN_DIR / tool_bin
            tool_exists = tool_path.exists() or shutil.which(tool_bin) is not None
        if tool_exists:
            if self.model.show_console:
                console.print(f"[dim]Skipping {tool_bin} (already installed)[/dim]")
            self._log_debug(f"Tool '{tool_bin}' is already installed, skipping")
            self.skipped_count += 1
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

            if post_install_cmd:
                self._log_info(f"Running post-install for '{tool_bin}'")
                post_exit, post_stdout, _post_stderr = await self._run_shell(
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
                        f"(exit {post_exit}): {(_post_stderr or post_stdout).strip()}"
                    )

        except Exception as exc:
            if self.model.show_console:
                console.print(f"[red]✗ Error installing {tool_bin}: {exc}[/red]")
            self._log_error(f"Error installing tool '{tool_bin}': {exc}")
            self.failed_count += 1

__all__ = ["ToolInstallation", "ToolInstallerRunner"]
