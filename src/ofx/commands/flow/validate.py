import logging
from pathlib import Path

from ofx.commands.ui_helpers import print_error, print_info, print_success
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class ValidateHandler:
    def run(self, workflow_name: str):
        """Validate a workflow configuration"""
        import yaml

        from ofx.models.workflow import Workflow

        logger.info(f"Validating workflow: {workflow_name}")

        print_info(
            "Workflow Validation",
            f"[bold]Validating:[/bold] [cyan]{workflow_name}[/cyan]",
        )

        src_object = yaml.safe_load(
            Path(f"{workflow_name.rstrip('.yml')}.yml").read_text()
        )
        try:
            Workflow.model_validate(src_object)
            print_success(
                "Validation Successful",
                f"Workflow '{workflow_name}' is valid!",
                {"Details": "All schema validations passed"},
            )
        except Exception as e:
            logger.error(f"Validation failed for workflow {workflow_name}: {e}")
            print_error(
                "Validation Error",
                "Validation failed",
                str(e),
            )
            raise e
