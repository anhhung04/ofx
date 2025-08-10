import json
import logging

from ofx.runner.workflow import FlowRunManager
from typing import Optional, List

logger = logging.getLogger("ofx")


class FlowRunHandler:
    def __init__(
        self,
        workflow_name: str,
        input: Optional[List[str]] = None,
        output: Optional[str] = None,
    ):
        self.workflow_name = workflow_name
        self.input = input
        self.output = output
        self.manager = FlowRunManager()

    async def run(self):
        self._process_inputs()
        task_id = self.manager.add(
            self.workflow_name, inputs=self.input, output=self.output
        )
        await self.manager.wait(task_id)

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
