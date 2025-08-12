import yaml
import logging

from ofx.models.workflow import Workflow
from pathlib import Path

logger = logging.getLogger("ofx")


class ValidateHandler:
    def run(self, workflow_name: str):
        """
        Validate a workflow configuration.
        """
        logger.info(f"Validating workflow: {workflow_name}")
        src_object = yaml.safe_load(
            Path(f"{workflow_name.rstrip('.yml')}.yml").read_text()
        )
        try:
            Workflow.model_validate(src_object)
        except Exception as e:
            logger.error(f"Validation failed for workflow {workflow_name}: {e}")
            raise e
        logger.info(f"Workflow {workflow_name} is valid.")
