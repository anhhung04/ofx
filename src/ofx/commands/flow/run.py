import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from ofx.commands.ui_helpers import inputs_table
from ofx.models.config import DurableRunConfig
from ofx.runner import run_workflow
from ofx.settings import (
    DEFAULT_WORKFLOWS_DIRS,
    SECRETS_DIR,
    TEMP_DIR,
    ensure_dir,
    get_console,
    settings,
)
from ofx.utils.secrets import load_secrets
from ofx.utils.workflow_utils import add_workflow_dir, find_workflow

logger = logging.getLogger(settings.app_branding)
console = get_console()


def get_tmp_dir(output: str = "") -> Path:
    """Get the temporary directory for workflow runs"""
    if output and Path(output).is_dir():
        return Path(output)
    return Path(
        tempfile.mkdtemp(
            prefix=f"run_{datetime.now().strftime('%d-%m-%Y_%H%M%S')}_",
            dir=ensure_dir(TEMP_DIR),
        )
    )


class FlowRunHandler:
    def __init__(
        self,
        workflow_name: str,
        input: list[str] | None = None,
        output: str = "",
        profile: bool = False,
        durable: bool | None = None,
        resume: bool | None = None,
        durable_backend: str | None = None,
        durable_redis_prefix: str | None = None,
    ):
        self.workflow_name = workflow_name
        self.preprocess_input = input or []
        self.output = get_tmp_dir(output)
        self.profile = profile
        self.durable = durable
        self.resume = resume
        self.durable_backend = durable_backend
        self.durable_redis_prefix = durable_redis_prefix

    async def run(self):
        import cProfile
        import pstats
        import time

        from rich.align import Align

        start_time = time.time()

        if self.profile:
            logger.info("Profiling enabled (detailed timing data will be collected).")
            profiler = cProfile.Profile()
            profiler.enable()

        try:
            self._process_inputs()

            logger.info("Workflow: %s", self.workflow_name)
            logger.info("Output: %s", self.output.as_posix())
            if self.input:
                console.print(Align.center(inputs_table(self.input)))

            durable_overrides = self._durable_overrides()
            result = await run_workflow(
                workflow=self.workflow_name,
                inputs=self.input,
                output_path=self.output,
                workflow_search_paths=DEFAULT_WORKFLOWS_DIRS,  # type: ignore
                quiet=False,
                durable_overrides=durable_overrides,
            )

            if result.status.value == "completed":
                logger.info("Workflow completed successfully!")
            else:
                logger.error("Workflow failed")

        finally:
            if self.profile:
                profiler.disable()
                end_time = time.time()

                total_time = end_time - start_time

                stats = pstats.Stats(profiler)
                stats.sort_stats("cumulative")

                profile_file = self.output / "profile.prof"
                profiler.dump_stats(str(profile_file))

                logger.info(
                    "Performance Summary: total_time=%.2fs profile=%s",
                    total_time,
                    profile_file,
                )

                logger.info("Top 10 functions by cumulative time:")
                stats.print_stats(10)

                logger.info("Top 10 functions by total time:")
                stats.print_stats("time", 10)

        return result

    def _process_inputs(self):
        from ofx.utils.args import parse_key_value_pairs

        try:
            self.input = parse_key_value_pairs(self.preprocess_input)
        except ValueError as e:
            raise e

    def _durable_overrides(self) -> DurableRunConfig | None:
        if (
            self.durable is None
            and self.resume is None
            and self.durable_backend is None
            and self.durable_redis_prefix is None
        ):
            return None

        config = DurableRunConfig()
        if self.durable is not None:
            config.enabled = self.durable
        if self.resume is not None:
            config.resume = self.resume
        if self.durable_backend is not None:
            config.backend = self.durable_backend
        if self.durable_redis_prefix is not None:
            config.redis_prefix = self.durable_redis_prefix
        return config
