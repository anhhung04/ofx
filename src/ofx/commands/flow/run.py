import os
import json
import logging

from ofx.settings import settings, SECRETS_DIR
from ofx.utils.misc import load_secrets
from ofx.runner.workflow import WorkflowRunner
from ofx.runner.base import RunContext
from ofx.settings import settings

from pathlib import Path
from notifiers.logging import NotificationHandler
from tabulate import tabulate
from typing import Optional, List

logger = logging.getLogger(settings.app_branding)


class FlowRunHandler:
    def __init__(
        self,
        workflow_name: str,
        input: Optional[List[str]] = None,
        output: Optional[str] = None,
    ):
        self.workflow_name = workflow_name
        self.input = input
        self.output = Path(output) if output else Path.cwd() / "out"

    async def run(self):
        self._process_inputs()
        input_display = self._render_input_as_table() if self.input else "None"
        logger.info(
            f"Starting to run workflow: '{self.workflow_name}' with input: {input_display}\nto output: '{self.output}'"
        )
        if settings.notify_provider:
            logger.info(f"Using notification provider: {settings.notify_provider}")
            if settings.notify_config:
                hdlr = NotificationHandler(
                    settings.notify_provider,
                    defaults=json.loads(settings.notify_config),
                )
                hdlr.setLevel(logging.INFO)
                hdlr.set_name("ofx.notification")
                logger.addHandler(hdlr)
            else:
                logger.warning("No notification configuration provided.")
        runner = WorkflowRunner(
            WorkflowRunner.find_flow(self.workflow_name),
            ctx=RunContext(
                inputs=self.input or {},
                output_path=self.output,
                secrets=load_secrets(SECRETS_DIR),
                envs=os.environ.copy(),
            ),
        )
        _ = await runner.run()
        assert runner.is_success, f"Workflow '{self.workflow_name}' failed."
        return runner.get_result()

    def _process_inputs(self):
        processed_inputs = {}
        for inp in self.input or []:
            try:
                key, value = inp.split("=", 1)
            except:
                raise ValueError(f"Invalid input format: {inp}. Expected key=value.")
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
            if key not in processed_inputs:
                processed_inputs[key] = [value]
            else:
                processed_inputs[key].append(value)
        for key in processed_inputs:
            if len(processed_inputs[key]) == 1:
                processed_inputs[key] = processed_inputs[key][0]
        logger.debug(f"Processed inputs: {processed_inputs}")
        self.input = processed_inputs

    def _render_input_as_table(self) -> str:
        """Renders the input data as a nicely formatted table if it contains any input."""
        if not self.input:
            return "None"

        # Convert input dictionary to a list of [key, value] pairs for tabulation
        table_data = []
        for key, value in self.input.items():
            # Handle complex values by converting them to JSON strings
            if isinstance(value, (dict, list)):
                try:
                    formatted_value = json.dumps(value)
                except:
                    formatted_value = str(value)
            else:
                formatted_value = str(value)

            table_data.append([key, formatted_value])

        return "\n" + tabulate(
            table_data, headers=["Parameter", "Value"], tablefmt="grid"
        )
