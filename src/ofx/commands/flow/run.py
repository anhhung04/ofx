import yaml
from ofx.settings import BASE_DATA_DIR
from ofx.runner.workflow import WorkflowRunner
from ofx.models.workflow import Workflow


class FlowRunHandler:
    def __init__(self, workflow_name: str):
        self._workflow_path = (
            BASE_DATA_DIR / "workflows" / f"{workflow_name.rstrip('.yml')}.yml"
        )
        assert self._workflow_path.exists(), f"Workflow {workflow_name} does not exist."
        self._workflow = Workflow.model_validate(
            yaml.safe_load(self._workflow_path.read_text())
        )
        self.workflow_name = workflow_name

    async def run(self):
        runner = WorkflowRunner(self._workflow)
        await runner.pre_run()
        await runner.run()
        await runner.post_run()
