import logging
from pathlib import Path

from ofx.commands.ui_helpers import print_error, print_info, print_success
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class ValidateHandler:
    def run(self, workflow_name: str):
        """Validate a workflow configuration"""
        from ofx.models.workflow import Workflow
        from ofx.utils.workflow_utils import find_workflow
        from ofx.settings import DEFAULT_WORKFLOWS_DIRS

        logger.info(f"Validating workflow: {workflow_name}")

        print_info(
            "Workflow Validation",
            f"[bold]Validating:[/bold] [cyan]{workflow_name}[/cyan]",
        )

        try:
             # Just loading it validates it via Pydantic model
            workflow = find_workflow(workflow_name, tuple(DEFAULT_WORKFLOWS_DIRS))
            print_success(
                "Validation Successful",
                f"Workflow '{workflow.name}' is valid!",
                {"Details": "All schema validations passed", "Path": str(workflow.workflow_path)},
            )
        except Exception as e:
            logger.error(f"Validation failed for workflow {workflow_name}: {e}")
            print_error(
                "Validation Error",
                "Validation failed",
                str(e),
            )
            raise e
