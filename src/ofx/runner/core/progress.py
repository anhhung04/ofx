import asyncio
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, Any, TYPE_CHECKING

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

if TYPE_CHECKING:
    from ofx.runner.runners import JobRunner


class ProgressTracker:
    def __init__(self, is_reused: bool = False):
        self._is_reused = is_reused
        self._progress = None
        self._progress_id = None

    def create_workflow_progress(self, name: str, total_steps: int) -> Progress:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=self._is_reused,
        )
        description = f"Running {'sub-' if self._is_reused else ''}workflow '[bold]{name}[/bold]'"
        self._progress_id = self._progress.add_task(
            description=description,
            total=total_steps,
        )
        return self._progress

    def update_workflow_progress(self, name: str, current_stage: int, total_stages: int, completed: int, total: int):
        if self._progress and self._progress_id is not None:
            self._progress.update(
                self._progress_id,
                description=f"Running {'sub-' if self._is_reused else ''}workflow '[bold]{name}[/bold]' - Stage {current_stage}/{total_stages}",
                completed=min(completed, total),
                refresh=True,
            )

    def complete_workflow_progress(self, name: str, total_steps: int):
        if self._progress and self._progress_id is not None:
            self._progress.update(
                self._progress_id,
                description=f"{'Sub-w' if self._is_reused else 'W'}orkflow '[bold]{name}[/bold]' completed",
                completed=total_steps,
                refresh=True,
            )

    def run_job_with_progress(
        self,
        job_id: str,
        job_name: str,
        total_steps: int,
        job_runner: "JobRunner",
        processor: ThreadPoolExecutor,
    ):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=True,
        ) as job_progress:
            running_msg = f"Running job '[bold]{job_name}[/bold]'"
            progress_task_id = job_progress.add_task(
                description=running_msg,
                total=total_steps,
            )
            job_task = processor.submit(asyncio.run, job_runner.run())
            while True:
                done, _ = wait([job_task], timeout=0.1, return_when=FIRST_COMPLETED)
                if len(done) > 0:
                    _ = job_task.result()
                    break
                job_progress.update(
                    progress_task_id,
                    completed=job_runner.processed_steps,
                    description=running_msg,
                    refresh=True,
                )

    def __enter__(self):
        if self._progress:
            return self._progress.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._progress:
            return self._progress.__exit__(exc_type, exc_val, exc_tb)
