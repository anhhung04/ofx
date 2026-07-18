"""Scheduling utilities for OFX framework."""

from collections import deque

def find_parallel_schedule(
    jobs: list[str], dependencies: list[tuple[str, str]]
) -> list[list[str]]:
    """Groups jobs into stages that can be run in parallel.

    Uses topological sorting with BFS for optimal parallelization.
    """
    graph: dict[str, list[str]] = {job: [] for job in jobs}
    in_degree: dict[str, int] = dict.fromkeys(jobs, 0)

    for prereq, job in dependencies:
        if prereq not in graph or job not in graph:
            continue
        graph[prereq].append(job)
        in_degree[job] += 1

    queue = deque([job for job in jobs if in_degree[job] == 0])

    parallel_schedule = []
    job_count = 0

    while queue:
        stage_size = len(queue)
        current_stage: list[str] = []

        for _ in range(stage_size):
            current_job = queue.popleft()
            current_stage.append(current_job)
            job_count += 1

            for next_job in graph[current_job]:
                in_degree[next_job] -= 1
                if in_degree[next_job] == 0:
                    queue.append(next_job)

        parallel_schedule.append(current_stage)

    if job_count != len(jobs):
        raise ValueError(
            "A circular dependency was detected. Cannot create a valid schedule."
        )

    return parallel_schedule
