import os
import git
from git.exc import GitCommandError
import typer
import json

from ofx.utils.misc import MetaSingleton
from ofx.settings import DEFAULT_WORKFLOWS_DIR, SECRETS_DIR, settings

from pathlib import Path


class InitHandler(metaclass=MetaSingleton):
    def _write_to_file(self, file_path: str | Path, content: str):
        if isinstance(file_path, str):
            with open(file_path, "w+") as file:
                file.writelines(content)
        else:
            file_path.write_text(content)

    def run(self):
        typer.echo("Unpacking workflows...")
        if not DEFAULT_WORKFLOWS_DIR.exists():
            DEFAULT_WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        if len(os.listdir(DEFAULT_WORKFLOWS_DIR)) == 0:
            typer.echo(
                f"Workflows will be unpacked to: {DEFAULT_WORKFLOWS_DIR}",
                err=True,
            )
            workflow_git_url = typer.prompt(
                "Enter the git URL of the workflow to unpack", default=""
            )
            if not workflow_git_url:
                typer.echo("No workflow URL provided. Exiting.", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"Cloning workflow from {workflow_git_url}...")
            try:
                git.Repo.clone_from(
                    workflow_git_url,
                    DEFAULT_WORKFLOWS_DIR,
                    depth=1,
                )
            except GitCommandError as e:
                typer.echo(f"Failed to clone workflow: {e}", err=True)
                raise typer.Exit(code=1)
        else:
            typer.echo(
                f"Workflows directory '{DEFAULT_WORKFLOWS_DIR}' is not empty. Skipping unpacking.",
                err=True,
            )
        is_use_noti = typer.confirm(
            "Do you want to use notifications for workflow runs?", default=False
        )
        if is_use_noti:
            notify_config_file = SECRETS_DIR / f"{settings.app_branding}_notify_config"
            provider = typer.prompt(
                "Enter the notification provider (one of 'telegram', 'discord', 'slack', 'pushover')",
                default="telegram",
            )
            self._write_to_file(
                SECRETS_DIR / f"{settings.app_branding}_notify_provider", provider
            )
            if provider.lower() == "telegram":
                token = typer.prompt("Enter the Telegram bot token")
                chat_id = typer.prompt("Enter the Telegram chat ID for notifications")
                self._write_to_file(
                    notify_config_file, json.dumps({"token": token, "chat_id": chat_id})
                )
            elif provider.lower() == "discord":
                webhook_url = typer.prompt(
                    "Enter the Discord webhook URL for notifications", default=""
                )
                self._write_to_file(
                    notify_config_file, json.dumps({"webhook_url": webhook_url})
                )
            elif provider.lower() == "slack":
                webhook_url = typer.prompt(
                    "Enter the Slack webhook URL for notifications", default=""
                )
                self._write_to_file(
                    notify_config_file, json.dumps({"webhook_url": webhook_url})
                )
            elif provider.lower() == "pushover":
                user_key = typer.prompt(
                    "Enter the Pushover user key for notifications", default=""
                )
                api_token = typer.prompt(
                    "Enter the Pushover API token for notifications", default=""
                )
                self._write_to_file(
                    notify_config_file,
                    json.dumps({"user_key": user_key, "api_token": api_token}),
                )
            else:
                typer.echo(
                    f"Unsupported notification provider: {provider}. Exiting.",
                    err=True,
                )
                raise typer.Exit(code=1)
