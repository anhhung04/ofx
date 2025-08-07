import json
import fcntl
from ofx.runner.base import BaseRunner, RunnerStatus
from ofx.models.workflow import Workflow, ConcurencyConfig
from ofx.settings import TEMP_DIR
from typing import Optional, Dict, Any

GROUP_REGISTRY = TEMP_DIR / "running_groups.json"


class WorkflowRunner(BaseRunner):
    _concurency: Optional[ConcurencyConfig] = None

    def __init__(self, workflow: Workflow):
        super().__init__(workflow.name)
        self._workflow = workflow
        self._init()

    async def run(self) -> Dict[str, Any]:
        print(f"Running workflow: {self._workflow.name}")
        print(self._workflow)

    async def pre_run(self):
        pass

    async def post_run(self):
        pass

    def _init(self):
        self._concurency = self._workflow.concurrency
        if self._concurency:
            self._register_group(self._concurency.group)

    def _register_group(self, group_name: str):
        with open(GROUP_REGISTRY, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                registry = json.load(f)
                if group_name not in registry:
                    registry[group_name] = {self._id: RunnerStatus.IDLE}
                else:
                    registry[group_name][self._id] = RunnerStatus.IDLE
                json.dump(registry, f, indent=4)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to register group {group_name} in {GROUP_REGISTRY}: {e}"
                )
            finally:
                f.close()
