import logging
from pathlib import Path

from rich.panel import Panel

from ofx.settings import get_console, settings

logger = logging.getLogger(settings.app_branding)
console = get_console()


class ValidateHandler:
    def run(self, workflow_name: str):
        """Validate a workflow configuration"""
        import yaml

        from ofx.models.workflow import Workflow

        logger.info(f"Validating workflow: {workflow_name}")

        console.print(Panel(
            f"[bold]Validating:[/bold] [cyan]{workflow_name}[/cyan]",
            title="[?] Workflow Validation",
            border_style="cyan"
        ))

        src_object = yaml.safe_load(
            Path(f"{workflow_name.rstrip('.yml')}.yml").read_text()
        )
        try:
            Workflow.model_validate(src_object)
            console.print(Panel(
                f"[bold green]Workflow '{workflow_name}' is valid![/bold green]\n"
                "[dim]All schema validations passed[/dim]",
                title="[bold green][OK] Validation Successful[/bold green]",
                border_style="green"
            ))
        except Exception as e:
            logger.error(f"Validation failed for workflow {workflow_name}: {e}")
            console.print(Panel(
                f"[bold red]Validation failed[/bold red]\n"
                f"[red]{e}[/red]",
                title="[bold red][X] Validation Error[/bold red]",
                border_style="red"
            ))
            raise e
