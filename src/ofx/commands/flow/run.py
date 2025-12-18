import json
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from tabulate import tabulate

from ofx.runner.base import RunContext
from ofx.runner.workflow import WorkflowRunner
from ofx.settings import SECRETS_DIR, settings
from ofx.utils.misc import load_secrets

logger = logging.getLogger(settings.app_branding)


class FlowRunHandler:
    def __init__(
        self,
        workflow_name: str,
        input: Optional[List[str]] = None,
        output: Optional[str] = None,
    ):
        self.workflow_name = workflow_name
        self.preprocess_input = input
        self.output = (
            Path(output) if output else Path(tempfile.mkdtemp(prefix="ofx")) / "results"
        )

    async def run(self):
        self._process_inputs()
        input_display = self._render_input_as_table() if self.input else "None"
        logger.info(
            f"Starting to run workflow: '{self.workflow_name}' with input: {input_display}\nto output: '{self.output.as_posix()}'"
        )
        runner = WorkflowRunner(
            WorkflowRunner.find_flow(self.workflow_name),
            ctx=RunContext(
                inputs=self.input,
                output_path=self.output,
                secrets=load_secrets(SECRETS_DIR),
                envs=os.environ.copy(),
            ),
        )
        res = await runner.run()
        if res.status.value != "completed":
            logger.error(
                f"Workflow run failed with status: {res.status}, error: {res.error}"
            )
        return runner.get_result()

    def _process_inputs(self):
        processed_inputs = {}
        for inp in self.preprocess_input or []:
            try:
                key, value = inp.split("=", 1)
            except Exception:
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

        table_data = []
        for key, value in self.input.items():
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
