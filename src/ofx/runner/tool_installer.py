"""Tool installer runner for installing workflow tools."""

import os
import shutil
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

from ofx.models.command import Command
from ofx.models.workflow import ToolConfig
from ofx.runner.commands.command import CommandRunner
from ofx.runner.context import RunContext, build_env_context
from ofx.runner.logging import prefix_log
from ofx.runner.runner import BaseRunner
from ofx.settings import TOOLS_BIN_DIR, ensure_dir

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

    def __str__(self):
        return f"ToolInstallation(tools={len(self.tools)} tools)"


class ToolInstallerRunner(BaseRunner[ToolInstallation]):
    """Runner for installing tools with template resolution support."""

    def __init__(
        self,
        tools: Mapping[str, str | dict[str, Any] | ToolConfig],
        ctx: RunContext,
        parent: BaseRunner | None = None,
        show_console: bool = True,
    ):
        tool_model = ToolInstallation(
            tools=dict(tools),
            show_console=show_console,
        )
        super().__init__(tool_model, ctx, parent)
        self._installed_count = 0
        self._skipped_count = 0
        self._failed_count = 0

    def _produce_log(self, message: str) -> str:
        """Produce a log message."""
        return prefix_log(message, "[ToolInstaller]")

    @property
    def installed_count(self) -> int:
        return self._installed_count

    @property
    def skipped_count(self) -> int:
        return self._skipped_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

    async def _do_run(self) -> None:
        """Install all configured tools."""
        if not self.model.tools:
            return

        current_path = self.ctx.envs.get("PATH", os.environ.get("PATH", ""))
        if str(TOOLS_BIN_DIR) not in current_path:
            ensure_dir(TOOLS_BIN_DIR)
            from ofx.runner.context import RunnerContextBuilder

            self.ctx = RunnerContextBuilder(self.ctx).with_env(
                {"PATH": f"{TOOLS_BIN_DIR}:{current_path}"}
            )

        for tool_bin, tool_config in self.model.tools.items():
            await self._install_tool(tool_bin, tool_config)

    def _tool_command_context(self) -> RunContext:
        """Create an isolated env-only context for tool-install commands."""
        return build_env_context(self.ctx.envs)

    def _make_command_runner(self, command: str) -> CommandRunner:
        """Create a command runner with the installer's current environment."""
        return CommandRunner(Command(cmd=command), self._tool_command_context())

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

        tool_exists = await self._check_tool_exists(tool_bin, check_cmd)
        if tool_exists:
            if self.model.show_console:
                console.print(f"[dim]Skipping {tool_bin} (already installed)[/dim]")
            self._log_debug(f"Tool '{tool_bin}' is already installed, skipping")
            self._skipped_count += 1
            return

        try:
            if self.model.show_console:
                console.print(f"[cyan]Installing {tool_bin}...[/cyan]")
            self._log_info(f"Installing tool '{tool_bin}' with command: {install_cmd}")

            runner = self._make_command_runner(install_cmd)
            result = await runner.run()

            if result.status.value != "completed":
                error_msg = f"Failed to install tool '{tool_bin}': {result.error}"
                if self.model.show_console:
                    console.print(
                        f"[red]✗ Failed to install {tool_bin}: {result.error}[/red]"
                    )
                self._log_error(error_msg)
                self._failed_count += 1
                return

            if self.model.show_console:
                console.print(f"[green]✓ Successfully installed {tool_bin}[/green]")
            self._log_info(f"Tool '{tool_bin}' installed successfully")
            self._installed_count += 1

            if post_install_cmd:
                await self._run_post_install(tool_bin, post_install_cmd)

        except Exception as exc:
            if self.model.show_console:
                console.print(f"[red]✗ Error installing {tool_bin}: {exc}[/red]")
            self._log_error(f"Error installing tool '{tool_bin}': {exc}")
            self._failed_count += 1

    async def _check_tool_exists(
        self,
        tool_bin: str,
        check_cmd: str | None = None,
    ) -> bool:
        """Check if a tool is already installed."""
        if check_cmd:
            self._log_debug(f"Checking tool '{tool_bin}' with: {check_cmd}")
            check_runner = self._make_command_runner(check_cmd)
            check_result = await check_runner.run()
            return (
                check_result.status.value == "completed"
                and check_result.outputs.get("exit_code") == 0
            )

        tool_path = TOOLS_BIN_DIR / tool_bin
        return tool_path.exists() or shutil.which(tool_bin) is not None

    async def _run_post_install(self, tool_bin: str, post_install_cmd: str) -> None:
        """Run a post-install command for a tool."""
        self._log_info(f"Running post-install for '{tool_bin}'")

        post_runner = self._make_command_runner(post_install_cmd)
        post_result = await post_runner.run()

        if post_result.status.value == "completed":
            stdout = post_result.outputs.get("stdout")
            if stdout:
                self._log_info(f"Post-install output for '{tool_bin}': {stdout}")
        else:
            self._log_warning(
                f"Post-install command for '{tool_bin}' failed: {post_result.error}"
            )


__all__ = ["ToolInstallation", "ToolInstallerRunner"]
