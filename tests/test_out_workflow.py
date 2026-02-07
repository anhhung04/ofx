import socket
from pathlib import Path

import pytest

from ofx.models.config import DurableRunConfig
from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
from ofx.runner.core import RunnerRegistryKeys
from ofx.utils.workflow_utils import find_workflow


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _insert_before_jobs(content: str, block: str) -> str:
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("jobs:"):
            lines.insert(idx, block.rstrip("\n"))
            return "\n".join(lines) + "\n"
    raise ValueError("jobs section not found")


def _insert_after_jobs(content: str, block: str) -> str:
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("jobs:"):
            lines.insert(idx + 1, block.rstrip("\n"))
            return "\n".join(lines) + "\n"
    raise ValueError("jobs section not found")


def _write_temp_workflow(
    tmp_path: Path,
    port: int,
    add_marker: bool = False,
    test_port: int | None = None,
    tools_block: str | None = None,
    extra_jobs: str | None = None,
) -> Path:
    source = Path(__file__).parents[1] / "out" / "test.yml"
    content = source.read_text()

    content = content.replace("3000", str(port))
    content = content.replace("sleep 5", "sleep 0.1")
    content = content.replace("sleep 2", "sleep 0.1")
    content = content.replace("time.sleep(2)", "time.sleep(0.1)")
    if test_port is not None:
        content = content.replace(
            f"http://localhost:{port}/test.sh",
            f"http://localhost:{test_port}/test.sh",
        )
    content = content.replace(
        'import time, requests\n          time.sleep(0.1)\n          print(requests.get("http://localhost:%s/test.sh").text)'
        % (test_port or port),
        "import time, requests\n"
        '          url = "http://localhost:%s/test.sh"\n'
        "          for _ in range(50):\n"
        "              try:\n"
        "                  resp = requests.get(url)\n"
        "                  if resp.status_code == 200:\n"
        "                      print(resp.text)\n"
        "                      break\n"
        "              except Exception:\n"
        "                  pass\n"
        "              time.sleep(0.1)\n"
        "          else:\n"
        '              raise RuntimeError("payload server not ready")'
        % (test_port or port),
    )
    if add_marker:
        content = content.replace(
            'echo "build_number=12345" >> $OFX_OUTPUTS',
            'echo "marker" >> {{ ctx.output_path }}/marker.txt\n'
            '          echo "build_number=12345" >> $OFX_OUTPUTS',
        )
    if tools_block:
        content = _insert_before_jobs(content, tools_block)
    if extra_jobs:
        content = _insert_after_jobs(content, extra_jobs)

    target = tmp_path / "durable_out.yml"
    target.write_text(content)
    return target


@pytest.mark.asyncio
async def test_out_workflow_outputs_and_alias(tmp_path: Path) -> None:
    port = _find_free_port()
    workflow_path = _write_temp_workflow(tmp_path, port)
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]

    workflow = find_workflow(str(workflow_path), tuple(workflow_dirs))
    ctx = RunContext(
        inputs={"t": True},
        output_path=tmp_path / "run",
        workflow_dirs=workflow_dirs,
        durable=DurableRunConfig(enabled=False),
    )

    runner = WorkflowRunner(workflow=workflow, ctx=ctx)
    result = await runner.run()

    assert result.status == RunnerStatus.COMPLETED
    assert runner.ctx.inputs.get("test") is True

    producer_runner = runner.runners["producer"]
    producer_outputs = await producer_runner.reg_get(RunnerRegistryKeys.OUTPUTS)
    assert producer_outputs is not None
    assert producer_outputs.get("build_number") == "12345"

    consumer_runner = runner.runners["consumer"]
    consumer_exec = await consumer_runner.reg_get(RunnerRegistryKeys.EXECUTION)
    assert consumer_exec is not None
    steps = consumer_exec.get("steps") or []
    assert len(steps) >= 2
    step_outputs = steps[0].get("outputs") or {}
    assert step_outputs.get("value") == "12345"


@pytest.mark.asyncio
async def test_out_workflow_execution_details(tmp_path: Path) -> None:
    port = _find_free_port()
    workflow_path = _write_temp_workflow(tmp_path, port)
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]

    workflow = find_workflow(str(workflow_path), tuple(workflow_dirs))
    ctx = RunContext(
        inputs={"t": True},
        output_path=tmp_path / "run",
        workflow_dirs=workflow_dirs,
        durable=DurableRunConfig(enabled=False),
    )

    runner = WorkflowRunner(workflow=workflow, ctx=ctx)
    result = await runner.run()

    assert result.status == RunnerStatus.COMPLETED

    test_runner = runner.runners["test"]
    test_exec = await test_runner.reg_get(RunnerRegistryKeys.EXECUTION)
    assert test_exec is not None
    assert test_exec.get("status") == "completed"
    steps = test_exec.get("steps") or []
    assert len(steps) == 1
    stdout = (steps[0].get("outputs") or {}).get("stdout") or ""
    assert "Hello, World!" in stdout
    assert "test job completed" in stdout


@pytest.mark.asyncio
async def test_out_workflow_durable_resume(tmp_path: Path) -> None:
    port = _find_free_port()
    workflow_path = _write_temp_workflow(tmp_path, port, add_marker=True)
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]
    output_path = tmp_path / "run"

    workflow = find_workflow(str(workflow_path), tuple(workflow_dirs))
    ctx = RunContext(
        inputs={"t": True},
        output_path=output_path,
        workflow_dirs=workflow_dirs,
        durable=DurableRunConfig(enabled=True, resume=True, backend="file"),
    )

    runner = WorkflowRunner(workflow=workflow, ctx=ctx)
    result = await runner.run()
    assert result.status == RunnerStatus.COMPLETED

    marker_path = output_path / "marker.txt"
    assert marker_path.exists()
    assert len(marker_path.read_text().splitlines()) == 1

    workflow = find_workflow(str(workflow_path), tuple(workflow_dirs))
    runner = WorkflowRunner(workflow=workflow, ctx=ctx)
    result = await runner.run()
    assert result.status == RunnerStatus.COMPLETED
    assert len(marker_path.read_text().splitlines()) == 1


@pytest.mark.asyncio
async def test_out_workflow_fails_on_test_job_error(tmp_path: Path) -> None:
    server_port = _find_free_port()
    bad_port = _find_free_port()
    workflow_path = _write_temp_workflow(tmp_path, server_port, test_port=bad_port)
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]

    workflow = find_workflow(str(workflow_path), tuple(workflow_dirs))
    ctx = RunContext(
        inputs={"t": True},
        output_path=tmp_path / "run",
        workflow_dirs=workflow_dirs,
        durable=DurableRunConfig(enabled=False),
    )

    runner = WorkflowRunner(workflow=workflow, ctx=ctx)
    result = await runner.run()

    assert result.status == RunnerStatus.FAILED
    test_runner = runner.runners["test"]
    test_exec = await test_runner.reg_get(RunnerRegistryKeys.EXECUTION)
    if test_exec is not None:
        assert test_exec.get("status") == "failed"


@pytest.mark.asyncio
async def test_out_workflow_matrix_job(tmp_path: Path) -> None:
    port = _find_free_port()
    extra_jobs = (
        "  matrix:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        x: [1, 2]\n"
        "    steps:\n"
        '      - run: echo "matrix={{ matrix.x }}" >> {{ ctx.output_path }}/matrix.txt\n'
    )
    workflow_path = _write_temp_workflow(tmp_path, port, extra_jobs=extra_jobs)
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]
    output_path = tmp_path / "run"

    workflow = find_workflow(str(workflow_path), tuple(workflow_dirs))
    ctx = RunContext(
        inputs={"t": True},
        output_path=output_path,
        workflow_dirs=workflow_dirs,
        durable=DurableRunConfig(enabled=False),
    )

    runner = WorkflowRunner(workflow=workflow, ctx=ctx)
    result = await runner.run()
    assert result.status == RunnerStatus.COMPLETED

    matrix_path = output_path / "matrix.txt"
    assert matrix_path.exists()
    lines = {line.strip() for line in matrix_path.read_text().splitlines()}
    assert lines == {"matrix=1", "matrix=2"}


@pytest.mark.asyncio
async def test_out_workflow_run_if_and_continue(tmp_path: Path) -> None:
    port = _find_free_port()
    extra_jobs = (
        "  conditional:\n"
        "    steps:\n"
        '      - run: /bin/sh -c "exit 1"\n'
        "        continue-on-error: true\n"
        "      - if: false\n"
        '        run: echo "skip" >> {{ ctx.output_path }}/conditional.txt\n'
        '      - run: echo "ok" >> {{ ctx.output_path }}/conditional.txt\n'
    )
    workflow_path = _write_temp_workflow(tmp_path, port, extra_jobs=extra_jobs)
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]
    output_path = tmp_path / "run"

    workflow = find_workflow(str(workflow_path), tuple(workflow_dirs))
    ctx = RunContext(
        inputs={"t": True},
        output_path=output_path,
        workflow_dirs=workflow_dirs,
        durable=DurableRunConfig(enabled=False),
    )

    runner = WorkflowRunner(workflow=workflow, ctx=ctx)
    result = await runner.run()
    assert result.status == RunnerStatus.COMPLETED

    conditional_path = output_path / "conditional.txt"
    assert conditional_path.exists()
    content = conditional_path.read_text()
    assert "ok" in content
    assert "skip" not in content

    conditional_runner = runner.runners["conditional"]
    conditional_exec = await conditional_runner.reg_get(RunnerRegistryKeys.EXECUTION)
    assert conditional_exec is not None
    assert conditional_exec.get("status") == "completed"
    assert conditional_exec.get("failed_steps") == [0]


@pytest.mark.asyncio
async def test_out_workflow_tools_install(tmp_path: Path) -> None:
    port = _find_free_port()
    tools_block = (
        "tools:\n"
        "  hello_tool:\n"
        "    install: |\n"
        "      mkdir -p /tmp/ofx_test_tools\n"
        "      printf '#!/bin/sh\\necho hello_tool' > /tmp/ofx_test_tools/hello_tool\n"
        "      chmod +x /tmp/ofx_test_tools/hello_tool\n"
        "    check: test -x /tmp/ofx_test_tools/hello_tool\n"
        "    post_install: echo 'hello_tool installed'\n"
    )
    extra_jobs = (
        "  tools_job:\n    steps:\n      - run: /tmp/ofx_test_tools/hello_tool\n"
    )
    workflow_path = _write_temp_workflow(
        tmp_path, port, tools_block=tools_block, extra_jobs=extra_jobs
    )
    workflow_dirs = [workflow_path.parent, Path.cwd().absolute()]
    output_path = tmp_path / "run"

    workflow = find_workflow(str(workflow_path), tuple(workflow_dirs))
    ctx = RunContext(
        inputs={"t": True},
        output_path=output_path,
        workflow_dirs=workflow_dirs,
        durable=DurableRunConfig(enabled=False),
    )

    runner = WorkflowRunner(workflow=workflow, ctx=ctx)
    result = await runner.run()
    assert result.status == RunnerStatus.COMPLETED

    tools_runner = runner.runners["tools_job"]
    tools_exec = await tools_runner.reg_get(RunnerRegistryKeys.EXECUTION)
    assert tools_exec is not None
    steps = tools_exec.get("steps") or []
    assert len(steps) == 1
    stdout = (steps[0].get("outputs") or {}).get("stdout") or ""
    assert "hello_tool" in stdout
