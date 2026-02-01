import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from ofx.commands.ui_helpers import inputs_table
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
    ):
        self.workflow_name = workflow_name
        self.preprocess_input = input or []
        self.output = get_tmp_dir(output)
        self.profile = profile

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

            if self.input:
                console.print(Align.center(inputs_table(self.input)))

            # Use the new programmatic API
            result = await run_workflow(
                workflow=self.workflow_name,
                inputs=self.input,
                output_path=self.output,
                workflow_search_paths=tuple(DEFAULT_WORKFLOWS_DIRS),
                quiet=False
            )

            if result.is_success:
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
            # Re-raise with same message logic if needed, or let bubble up
            # The utility raises ValueError with clear message
            raise e
